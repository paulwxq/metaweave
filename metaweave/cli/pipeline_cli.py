"""pipeline 命令组 — 统一编排 generate（产物生成）与 load（数据加载）

近似等价于按顺序执行以下能力：
- pipeline generate: ddl → md → generate-domains → json_llm → dim_config
                     → rel_llm → cql → sql-rag generate → sql-rag validate
- pipeline load:     cql → table_schema → sql [→ dim_value]

pipeline 内部通过代码直接调用底层模块，并非逐条拼接 CLI 命令。
"""

import copy
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

import click
import yaml

from metaweave.utils.file_utils import get_project_root, clear_dir_contents
from metaweave.utils.logger import set_current_step

logger = logging.getLogger("metaweave.cli")


# =====================================================================
# 异常 & 上下文
# =====================================================================


class _StepError(Exception):
    """pipeline 步骤执行失败"""

    def __init__(self, step_name: str, errors: list[str] | None = None):
        self.step_name = step_name
        self.errors = errors or []
        super().__init__(f"步骤失败 [{step_name}]")


@dataclass
class _PipelineContext:
    """pipeline generate 的步骤间共享上下文"""

    project_root: Path
    config_path: Path  # metadata_config.yaml 绝对路径
    loaded_config: dict  # metadata_config 解析结果
    domains_path: Path  # db_domains.yaml 绝对路径
    description: str | None  # --description 参数
    regenerate_configs: bool  # --regenerate-configs 参数

    # 步骤间传递的中间产物（由步骤执行时填充）
    sql_rag_gen_result: Any = None  # 步骤 8 产出，供步骤 9 使用
    sql_rag_cfg: dict = field(default_factory=dict)  # 步骤 8 加载
    llm_service: Any = None  # 步骤 8 创建，供步骤 9 修复使用
    _sql_connector: Any = None  # 步骤 8 创建的 DB 连接，步骤 9 使用后关闭


# =====================================================================
# 常量
# =====================================================================

GENERATE_STEPS = [
    "ddl",
    "md",
    "generate-domains",
    "json_llm",
    "dim_config",
    "rel_llm",
    "cql",
    "sql-rag-generate",
    "sql-rag-validate",
]

LOAD_STEPS = ["cql", "table_schema", "sql"]


# =====================================================================
# 辅助函数
# =====================================================================


def _resolve(path_str: str, project_root: Path) -> Path:
    """相对路径基于项目根目录解析为绝对路径"""
    p = Path(path_str)
    if not p.is_absolute():
        p = project_root / p
    return p


def _resolve_output_dir(sub: str, loaded_config: dict) -> Path:
    """解析 output 子目录的绝对路径。

    Args:
        sub: 子目录名（ddl/md/json/rel/cql）
        loaded_config: metadata_config 字典
    """
    project_root = get_project_root()
    output_cfg = loaded_config.get("output", {})
    output_dir = Path(output_cfg.get("output_dir", "output"))
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir

    key_map = {
        "ddl": "ddl_directory",
        "md": "markdown_directory",
        "json": "json_directory",
        "rel": "rel_directory",
        "cql": "cql_directory",
    }
    key = key_map.get(sub)
    if key and output_cfg.get(key):
        d = Path(output_cfg[key])
        if not d.is_absolute():
            d = project_root / d
        return d
    return output_dir / sub


def _resolve_md_dir(loaded_config: dict) -> Path:
    """解析 markdown 输出目录路径"""
    return _resolve_output_dir("md", loaded_config)


def _load_yaml(path: Path) -> dict:
    """加载 YAML 文件，不存在返回空字典"""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _backup_config_file(file_path: Path) -> Path:
    """备份配置文件，返回备份路径。

    命名规则：<原文件名>.bak_yyyyMMdd_HHmmss
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = file_path.parent / f"{file_path.name}.bak_{ts}"
    shutil.copy2(file_path, backup_path)
    logger.info("已备份: %s -> %s", file_path, backup_path)
    return backup_path


def _clean_all_output_dirs(
    loaded_config: dict, project_root: Path
) -> None:
    """清空全部 output 子目录。

    Args:
        loaded_config: 已加载的 metadata_config 字典
        project_root: 项目根目录
    """
    output_cfg = loaded_config.get("output", {})
    output_dir = Path(output_cfg.get("output_dir", "output"))
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir

    # 1. 清理 metadata 相关 output 子目录
    dir_keys = {
        "ddl": "ddl_directory",
        "md": "markdown_directory",
        "json": "json_directory",
        "rel": "rel_directory",
        "cql": "cql_directory",
    }
    for sub, key in dir_keys.items():
        d = output_cfg.get(key)
        if d:
            d = Path(d)
            if not d.is_absolute():
                d = project_root / d
        else:
            d = output_dir / sub
        if d.exists():
            clear_dir_contents(d)
            logger.debug("已清空: %s", d)

    # 2. 清理 sql 输出目录（从 metadata_config 的 sql_rag 段读取）
    sql_rag_cfg = loaded_config.get("sql_rag", {})
    sql_output_dir = _resolve(
        sql_rag_cfg.get("generation", {}).get("output_dir", "output/sql"),
        project_root,
    )
    if sql_output_dir.exists():
        clear_dir_contents(sql_output_dir)
        logger.debug("已清空: %s", sql_output_dir)


def _log_step_failure(
    step_name: str, message: str, errors: list[str] | None = None
) -> None:
    """记录步骤失败日志（不抛出异常）"""
    logger.error("步骤失败 [%s]: %s", step_name, message)
    click.echo(f"❌ 步骤失败 [{step_name}]: {message}", err=True)
    if errors:
        for e in errors[:10]:
            logger.error("  - %s", e)
            click.echo(f"  - {e}", err=True)
        if len(errors) > 10:
            msg = f"  ... 还有 {len(errors) - 10} 个错误"
            logger.error(msg)
            click.echo(msg, err=True)


# =====================================================================
# 步骤函数
# =====================================================================


def _step_ddl(ctx: _PipelineContext) -> None:
    from metaweave.core.metadata.generator import MetadataGenerator

    generator = MetadataGenerator(ctx.config_path)
    result = generator.generate(step="ddl")
    if not result.success or result.failed_tables > 0:
        raise _StepError("ddl", result.errors)


def _step_md(ctx: _PipelineContext) -> None:
    from metaweave.core.metadata.generator import MetadataGenerator

    ddl_dir = _resolve_output_dir("ddl", ctx.loaded_config)
    ddl_files = list(ddl_dir.glob("*.sql")) if ddl_dir.exists() else []
    if not ddl_files:
        raise _StepError("md", [f"DDL 目录为空: {ddl_dir}"])

    generator = MetadataGenerator(ctx.config_path)
    result = generator.generate(step="md")
    if not result.success or result.failed_tables > 0:
        raise _StepError("md", result.errors)


def _step_generate_domains(ctx: _PipelineContext) -> None:
    from metaweave.core.metadata.domain_generator import DomainGenerator

    if ctx.domains_path.exists() and not ctx.regenerate_configs:
        logger.warning("%s 已存在，跳过生成。", ctx.domains_path)
        logger.warning("如需备份旧文件并重新生成，请使用 --regenerate-configs。")
        return

    if ctx.domains_path.exists() and ctx.regenerate_configs:
        _backup_config_file(ctx.domains_path)

    generator = DomainGenerator(
        config=ctx.loaded_config,
        yaml_path=str(ctx.domains_path),
        md_context_dir=str(_resolve_md_dir(ctx.loaded_config)),
        md_context_mode="name_comment",
        md_context_limit=None,
    )
    generated = generator.generate_from_context(user_description=ctx.description)
    generator.write_to_yaml(generated)


def _step_json_llm(ctx: _PipelineContext) -> None:
    from metaweave.core.metadata.generator import MetadataGenerator
    from metaweave.core.metadata.json_llm_enhancer import JsonLlmEnhancer

    # 阶段 1: 生成全量 JSON
    click.echo("📊 阶段 1/2: 生成全量 JSON（step=json）...")
    generator = MetadataGenerator(ctx.config_path)
    result_a = generator.generate(step="json")
    if not result_a.success or result_a.failed_tables > 0:
        raise _StepError("json_llm", ["阶段 1 (json) 失败"] + result_a.errors)

    # 阶段 2: LLM 增强
    json_dir = generator.formatter.json_dir.resolve()
    json_files = [
        Path(p)
        for p in result_a.output_files
        if Path(p).suffix == ".json" and Path(p).resolve().parent == json_dir
    ]
    if not json_files:
        raise _StepError("json_llm", ["阶段 1 未生成任何 JSON 文件"])

    cli_config = copy.deepcopy(generator.config)
    if "llm" in cli_config and "langchain_config" in cli_config["llm"]:
        cli_config["llm"]["langchain_config"]["use_async"] = False

    click.echo("🤖 阶段 2/2: LLM 增强处理（原地写回 output/json）...")
    enhancer = JsonLlmEnhancer(cli_config)
    enhancer.enhance_json_files(json_files)


def _step_dim_config(ctx: _PipelineContext) -> None:
    from metaweave.core.dim_value.config_generator import DimTableConfigGenerator

    # 从 metadata_config 的 loaders 段获取 dim_tables.yaml 目标路径
    loaders_cfg = ctx.loaded_config.get("loaders", {})
    dim_tables_path = _resolve(
        loaders_cfg.get("dim_loader", {}).get("config_file", "configs/dim_tables.yaml"),
        ctx.project_root,
    )

    # 配置型文件保守处理
    if dim_tables_path.exists() and not ctx.regenerate_configs:
        logger.warning("%s 已存在，跳过生成。", dim_tables_path)
        logger.warning("如需备份旧文件并重新生成，请使用 --regenerate-configs。")
        return

    if dim_tables_path.exists() and ctx.regenerate_configs:
        _backup_config_file(dim_tables_path)

    json_dir = _resolve_output_dir("json", ctx.loaded_config)
    gen = DimTableConfigGenerator(json_dir=json_dir, output_path=dim_tables_path)
    gen.generate()


def _step_rel_llm(ctx: _PipelineContext) -> None:
    from metaweave.core.metadata.connector import DatabaseConnector
    from metaweave.core.relationships.llm_relationship_discovery import (
        LLMRelationshipDiscovery,
    )
    from metaweave.core.relationships.writer import RelationshipWriter
    from metaweave.core.domains.resolver import DomainResolver

    connector = DatabaseConnector(ctx.loaded_config.get("database", {}))
    try:
        rel_cfg = ctx.loaded_config.get("relationships") or {}
        effective_domain = rel_cfg.get("domain")
        effective_cross_domain = rel_cfg.get("cross_domain")

        if not effective_domain:
            effective_cross_domain = False
        else:
            effective_cross_domain = bool(effective_cross_domain)

        domain_resolver = None
        if effective_domain:
            if not ctx.domains_path.exists():
                raise _StepError("rel_llm", [
                    f"yaml 配置 relationships.domain={effective_domain} 已生效，"
                    f"但 domains 配置文件不存在: {ctx.domains_path}。"
                    f"请先执行 generate-domains 步骤，或将 relationships.domain 设为 null"
                ])
            domain_resolver = DomainResolver(ctx.domains_path)
            if not domain_resolver.get_all_domains():
                raise _StepError("rel_llm", [
                    f"yaml 配置 relationships.domain={effective_domain} 已生效，"
                    f"但 {ctx.domains_path} 中 domains 列表为空。"
                    f"请先执行 generate-domains 步骤生成 domain 配置"
                ])

        discovery = LLMRelationshipDiscovery(
            config=ctx.loaded_config,
            connector=connector,
            domain_filter=effective_domain,
            cross_domain=effective_cross_domain,
            domain_resolver=domain_resolver,
        )

        if not discovery.json_dir.exists():
            raise _StepError(
                "rel_llm", [f"json 目录不存在: {discovery.json_dir}"]
            )

        relations, rejected_count, extra_statistics = discovery.discover()

        writer = RelationshipWriter(ctx.loaded_config)
        writer.write_results(
            relations=relations,
            suppressed=[],
            config=ctx.loaded_config,
            tables=discovery.tables,
            generated_by="rel_llm",
            extra_statistics=extra_statistics,
        )
    finally:
        connector.close()


def _step_cql(ctx: _PipelineContext) -> None:
    from metaweave.core.cql_generator.generator import CQLGenerator
    from metaweave.core.domains.resolver import DomainResolver

    cql_resolver = (
        DomainResolver(ctx.domains_path) if ctx.domains_path.exists() else None
    )
    generator = CQLGenerator(ctx.config_path, domain_resolver=cql_resolver)
    result = generator.generate(step_name="cql")
    if not result.success:
        raise _StepError("cql", result.errors)


def _step_sql_rag_generate(ctx: _PipelineContext) -> None:
    from metaweave.core.metadata.connector import DatabaseConnector
    from metaweave.services.llm_service import LLMService
    from metaweave.core.sql_rag.generator import QuestionSQLGenerator

    # 提前创建 DB 连接（步骤 9 需要用于 EXPLAIN）
    ctx._sql_connector = DatabaseConnector(ctx.loaded_config.get("database", {}))

    # 从 metadata_config 的 sql_rag 段读取配置
    sql_rag_cfg = ctx.loaded_config.get("sql_rag", {})

    generation_config = sql_rag_cfg.get("generation", {})

    llm_service = LLMService(ctx.loaded_config.get("llm", {}))
    generator = QuestionSQLGenerator(llm_service, generation_config)

    md_dir = _resolve_md_dir(ctx.loaded_config)

    gen_result = generator.generate(
        domains_config_path=str(ctx.domains_path),
        md_dir=str(md_dir),
    )
    if not gen_result.success:
        raise _StepError(
            "sql-rag-generate",
            ["Question-SQL 生成失败（全部 domain 均无有效产出）"],
        )

    # 域级失败判定
    failed_domains = [
        d for d, count in gen_result.domain_stats.items() if count == 0
    ]
    if failed_domains:
        logger.warning(
            "以下 domain 生成数为 0（可能存在异常）: %s", failed_domains
        )

    # 存入上下文供步骤 9 使用
    ctx.sql_rag_gen_result = gen_result
    ctx.sql_rag_cfg = sql_rag_cfg
    ctx.llm_service = llm_service


def _step_sql_rag_validate(ctx: _PipelineContext) -> None:
    from metaweave.core.sql_rag.validator import SQLValidator

    try:
        validation_config = ctx.sql_rag_cfg.get("validation", {})
        enable_repair = validation_config.get("enable_sql_repair", False)

        repair_llm = ctx.llm_service if enable_repair else None

        md_dir_str = str(_resolve_md_dir(ctx.loaded_config))
        rel_dir_str = str(_resolve_output_dir("rel", ctx.loaded_config))

        validator = SQLValidator(
            connector=ctx._sql_connector,
            config=validation_config,
            llm_service=repair_llm,
            md_dir=md_dir_str,
            rel_dir=rel_dir_str,
        )

        stats = validator.validate_file(
            input_file=ctx.sql_rag_gen_result.output_file,
            enable_repair=enable_repair,
        )

        # 校验后质量判定
        final_valid = stats["valid"] + stats["repair_stats"]["successful"]
        final_invalid = stats["total"] - final_valid
        if final_invalid > 0:
            if enable_repair:
                # 启用修复时，修复失败的条目已被自动从文件中删除
                # 但 stats["total"] 仍为原始总数，因此 final_invalid 可能大于 0
                # 这表示有条目修复失败并已从最终文件中移除，不影响后续加载质量
                logger.warning(
                    "SQL 校验完成（已启用修复）：原始 %d 条，有效 %d 条，"
                    "修复失败 %d 条（已从文件删除）",
                    stats["total"],
                    final_valid,
                    final_invalid,
                )
            else:
                # 未启用修复时，无效 SQL 仍保留在文件中
                # SQLExampleLoader 不校验 SQL 有效性，会原样装载进向量库
                # 因此必须在此处阻断，避免污染向量库
                raise _StepError(
                    "sql-rag-validate",
                    [
                        f"校验完成但存在 {final_invalid} 条无效 SQL（未启用修复）",
                        "请启用 metadata_config.yaml -> sql_rag.validation.enable_sql_repair"
                        " 或手工修正后重新执行",
                    ],
                )
    finally:
        # 关闭步骤 8 创建的 DB 连接
        if ctx._sql_connector is not None:
            ctx._sql_connector.close()
            ctx._sql_connector = None


# =====================================================================
# 步骤分发
# =====================================================================

_STEP_MAP = {
    "ddl": _step_ddl,
    "md": _step_md,
    "generate-domains": _step_generate_domains,
    "json_llm": _step_json_llm,
    "dim_config": _step_dim_config,
    "rel_llm": _step_rel_llm,
    "cql": _step_cql,
    "sql-rag-generate": _step_sql_rag_generate,
    "sql-rag-validate": _step_sql_rag_validate,
}


def _run_generate_step(step_name: str, ctx: _PipelineContext) -> None:
    fn = _STEP_MAP[step_name]
    fn(ctx)


# =====================================================================
# Click 命令组
# =====================================================================


@click.group(name="pipeline")
def pipeline_command():
    """统一编排命令：生成全部产物或加载到目标库"""
    pass


# =====================================================================
# pipeline generate
# =====================================================================


@pipeline_command.command(name="generate")
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    default="configs/metadata_config.yaml",
    show_default=True,
    help="主配置文件路径（metadata_config.yaml）",
)
@click.option(
    "--domains-config",
    type=click.Path(exists=False),
    default="configs/db_domains.yaml",
    show_default=True,
    help="domain 配置文件路径",
)
@click.option(
    "--description",
    type=str,
    default=None,
    help="可选：生成 db_domains.yaml 时的业务背景说明",
)
@click.option(
    "--regenerate-configs",
    is_flag=True,
    default=False,
    help="备份并重新生成配置型 YAML 文件（db_domains.yaml, dim_tables.yaml）",
)
@click.option(
    "--clean",
    is_flag=True,
    default=False,
    help="清理 output/* 目录后重新生成",
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="启用调试模式",
)
def pipeline_generate(
    config,
    domains_config,
    description,
    regenerate_configs,
    clean,
    debug,
):
    """生成全部产物（9 步串行）"""
    from services.config_loader import ConfigLoader
    from metaweave.services.llm_config_resolver import (
        _validate_declared_module_llm_paths,
        _validate_nonstandard_llm_paths,
    )

    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

    project_root = get_project_root()
    config_path = _resolve(config, project_root)
    loaded_config = ConfigLoader(str(config_path)).load()
    _validate_declared_module_llm_paths(loaded_config)
    _validate_nonstandard_llm_paths(loaded_config)

    ctx = _PipelineContext(
        project_root=project_root,
        config_path=config_path,
        loaded_config=loaded_config,
        domains_path=_resolve(domains_config, project_root),
        description=description,
        regenerate_configs=regenerate_configs,
    )

    parent_step = "pipeline-generate"
    set_current_step(parent_step)

    logger.info("🚀 开始 pipeline generate")
    logger.info(
        "🧭 调度顺序: %s", " -> ".join(GENERATE_STEPS)
    )

    click.echo("🚀 开始 pipeline generate")
    click.echo(f"🧭 调度顺序: {' -> '.join(GENERATE_STEPS)}")

    # --clean 提示
    if clean:
        _clean_all_output_dirs(ctx.loaded_config, ctx.project_root)
        click.echo("🧹 已清空全部 output 子目录")
    else:
        logger.info("未启用 --clean，将覆盖同名文件，但不会删除历史产物。")
        logger.warning(
            "如果本次生成范围与上次不同，目录中可能残留旧文件；"
            "如需全量重建，请使用 --clean。"
        )

    try:
        for step_name in GENERATE_STEPS:
            set_current_step(step_name)
            logger.info("▶️  正在启动步骤: %s", step_name)

            click.echo("")
            click.echo("=" * 60)
            click.echo(f"▶️  开始步骤: {step_name}")
            click.echo("=" * 60)

            try:
                _run_generate_step(step_name, ctx)
            except _StepError as e:
                _log_step_failure(e.step_name, str(e), e.errors)
                raise click.Abort()
            except Exception as e:
                _log_step_failure(step_name, str(e))
                logger.error(
                    "步骤内部未捕获异常 [%s]", step_name, exc_info=True
                )
                raise click.Abort()

            set_current_step(parent_step)
            click.echo(f"✅ {step_name} 完成")

        click.echo("")
        click.echo("✨ pipeline generate 全部完成！")
    except click.Abort:
        set_current_step(parent_step)
        raise
    finally:
        # 兜底：确保 sql-rag DB 连接被关闭
        if ctx._sql_connector is not None:
            try:
                ctx._sql_connector.close()
            except Exception:
                logger.warning("关闭 sql-rag DB connector 时异常", exc_info=True)


# =====================================================================
# pipeline load
# =====================================================================


@pipeline_command.command(name="load")
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    default="configs/metadata_config.yaml",
    show_default=True,
    help="主配置文件路径（metadata_config.yaml）",
)
@click.option(
    "--with-dim-values",
    is_flag=True,
    default=False,
    help="是否加载 dim_value（需要已确认 dim_tables.yaml）",
)
@click.option(
    "--clean",
    is_flag=True,
    default=False,
    help="加载前清理目标库/集合",
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="启用调试模式",
)
def pipeline_load(config, with_dim_values, clean, debug):
    """加载产物到目标库（3+1 步串行）"""
    from metaweave.core.loaders.factory import LoaderFactory
    from services.config_loader import ConfigLoader

    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

    project_root = get_project_root()
    config_path = _resolve(config, project_root)

    # 通过 ConfigLoader 加载主配置（支持环境变量替换）
    full_config = ConfigLoader(str(config_path)).load()

    # 从主配置切出 loaders 段，作为 loader 的 config dict
    loader_cfg = full_config.get("loaders", {})
    # 保留 metadata_config_file 引用（dim_loader、table_schema_loader 需要）
    loader_cfg["metadata_config_file"] = str(config_path)

    # 动态补全 sql_loader.input_file（如配置中为空则从 database.database 拼出）
    sql_loader_cfg = loader_cfg.get("sql_loader", {})
    if not sql_loader_cfg.get("input_file"):
        db_name = full_config.get("database", {}).get("database", "")
        if db_name:
            sql_output_dir = full_config.get("sql_rag", {}).get(
                "generation", {}
            ).get("output_dir", "output/sql")
            sql_input_path = _resolve(sql_output_dir, project_root) / f"qs_{db_name}_pair.json"
            if "sql_loader" not in loader_cfg:
                loader_cfg["sql_loader"] = {}
            loader_cfg["sql_loader"]["input_file"] = str(sql_input_path)
            logger.info("sql_loader.input_file 动态解析为: %s", sql_input_path)

    steps = list(LOAD_STEPS)
    if with_dim_values:
        # 前置校验：dim_tables.yaml 必须存在
        dim_cfg_file = loader_cfg.get("dim_loader", {}).get(
            "config_file", "configs/dim_tables.yaml"
        )
        dim_cfg_path = _resolve(dim_cfg_file, project_root)
        if not dim_cfg_path.exists():
            raise click.UsageError(
                f"dim_tables.yaml 不存在: {dim_cfg_path}\n"
                f"请先执行 pipeline generate 或手工创建该文件"
            )
        steps.append("dim_value")

    parent_step = "pipeline-load"
    set_current_step(parent_step)

    logger.info("🚀 开始 pipeline load")
    logger.info("🧭 调度顺序: %s", " -> ".join(steps))

    click.echo("🚀 开始 pipeline load")
    click.echo(f"🧭 调度顺序: {' -> '.join(steps)}")

    if clean:
        click.echo("⚠️  --clean 将在每个 loader 执行前清理对应目标库/集合")

    try:
        for step_name in steps:
            set_current_step(step_name)

            click.echo("")
            click.echo("=" * 60)
            click.echo(f"▶️  开始加载: {step_name}")
            click.echo("=" * 60)

            try:
                loader = LoaderFactory.create(step_name, loader_cfg)

                if not loader.validate():
                    raise _StepError(step_name, [f"{step_name} loader 验证失败"])

                result = loader.load(clean=clean)
                if not result.get("success"):
                    raise _StepError(
                        step_name,
                        [result.get("message", "加载失败（未知原因）")],
                    )
            except _StepError as e:
                _log_step_failure(e.step_name, str(e), e.errors)
                raise click.Abort()
            except Exception as e:
                _log_step_failure(step_name, str(e))
                logger.error(
                    "步骤内部未捕获异常 [%s]", step_name, exc_info=True
                )
                raise click.Abort()

            set_current_step(parent_step)
            click.echo(f"✅ {step_name} 加载完成")

        click.echo("")
        click.echo("✨ pipeline load 全部完成！")
    except click.Abort:
        set_current_step(parent_step)
        raise
