"""SQL RAG CLI 子命令

提供 Question-SQL 生成、校验、加载的命令行接口。
"""

import logging
from pathlib import Path
from typing import Optional

import click

from metaweave.utils.file_utils import get_project_root
from metaweave.utils.logger import set_current_step
from services.config_loader import ConfigLoader

logger = logging.getLogger("metaweave.cli")


def _load_main_config(config_path: str, project_root: Path) -> dict:
    """用 ConfigLoader 加载主配置文件（metadata_config.yaml），支持 ${ENV_VAR} 展开。

    加载后立即执行全局预检（白名单 + 非标准路径），与 metadata_cli / pipeline_cli 行为一致。
    """
    from metaweave.services.llm_config_resolver import (
        _validate_declared_module_llm_paths,
        _validate_nonstandard_llm_paths,
    )

    path = _resolve_path(config_path, project_root)
    full_config = ConfigLoader(str(path)).load()
    _validate_declared_module_llm_paths(full_config)
    _validate_nonstandard_llm_paths(full_config)
    return full_config


@click.group(name="sql-rag")
def sql_rag_command():
    """SQL RAG 样例生成与加载

    基于表结构文档和业务主题域，生成 Question-SQL 训练样例，
    经 SQL EXPLAIN 校验后向量化加载到 Milvus。
    """
    pass


@sql_rag_command.command()
@click.option(
    "--config", "-c",
    type=click.Path(exists=True),
    default="configs/metadata_config.yaml",
    show_default=True,
    help="主配置文件路径（metadata_config.yaml）",
)
@click.option(
    "--domains-config",
    type=click.Path(exists=True),
    default="configs/db_domains.yaml",
    show_default=True,
    help="db_domains.yaml 主题域配置路径",
)
@click.option(
    "--md-dir",
    type=click.Path(exists=True),
    default="output/md",
    show_default=True,
    help="Markdown 表结构目录",
)
@click.option(
    "--clean", is_flag=True,
    help="生成前删除当前库的旧样例文件",
)
@click.option("--debug", is_flag=True, help="启用调试模式")
def generate(config: str, domains_config: str, md_dir: str, clean: bool, debug: bool):
    """生成 Question-SQL 训练样例"""
    if debug:
        logging.getLogger("metaweave").setLevel(logging.DEBUG)

    set_current_step("sql-rag-generate")
    project_root = get_project_root()

    # 加载主配置
    main_config = _load_main_config(config, project_root)
    sql_rag_cfg = main_config.get("sql_rag", {})
    generation_config = sql_rag_cfg.get("generation", {})

    # 初始化 LLMService（通过统一解析器，支持 sql_rag.llm 深合并覆盖）
    from metaweave.services.llm_service import LLMService
    from metaweave.services.llm_config_resolver import resolve_module_llm_config

    llm_config = resolve_module_llm_config(main_config, "sql_rag.llm")
    llm_service = LLMService(llm_config)

    # 创建生成器
    from metaweave.core.sql_rag.generator import QuestionSQLGenerator

    generator = QuestionSQLGenerator(llm_service, generation_config)

    # clean: 删除当前库的样例文件
    if clean:
        import yaml
        domains_path = _resolve_path(domains_config, project_root)
        with open(domains_path, "r", encoding="utf-8") as f:
            domains_cfg = yaml.safe_load(f)
        db_name = domains_cfg.get("database", {}).get("name", "unknown")
        generator.clean_output(db_name)
        click.echo(f"已清理 {db_name} 的旧样例文件")

    # 执行生成
    click.echo("开始生成 Question-SQL...")
    domains_path = _resolve_path(domains_config, project_root)
    md_dir_path = _resolve_path(md_dir, project_root)

    result = generator.generate(
        domains_config_path=str(domains_path),
        md_dir=str(md_dir_path),
    )

    if result.success:
        click.echo(f"生成完成: 共 {result.total_generated} 条 Question-SQL")
        click.echo(f"输出文件: {result.output_file}")
        for domain, count in result.domain_stats.items():
            click.echo(f"  {domain}: {count} 条")
    else:
        click.echo("生成失败，请查看日志", err=True)
        raise click.Abort()


@sql_rag_command.command()
@click.option(
    "--config", "-c",
    type=click.Path(exists=True),
    default="configs/metadata_config.yaml",
    show_default=True,
    help="主配置文件路径（metadata_config.yaml）",
)
@click.option(
    "--input", "-i", "input_file",
    type=click.Path(exists=True),
    default=None,
    help="指定输入文件（覆盖默认路径）",
)
@click.option(
    "--enable_sql_repair",
    type=click.BOOL,
    default=None,
    help="覆盖配置文件中的 enable_sql_repair（true/false）",
)
@click.option("--debug", is_flag=True, help="启用调试模式")
def validate(
    config: str,
    input_file: Optional[str],
    enable_sql_repair: Optional[bool],
    debug: bool,
):
    """校验 Question-SQL 中的 SQL 语句"""
    if debug:
        logging.getLogger("metaweave").setLevel(logging.DEBUG)

    set_current_step("sql-rag-validate")
    project_root = get_project_root()

    # 加载主配置
    main_config = _load_main_config(config, project_root)
    sql_rag_cfg = main_config.get("sql_rag", {})
    validation_config = sql_rag_cfg.get("validation", {})

    # 确定输入文件
    if not input_file:
        generation_config = sql_rag_cfg.get("generation", {})
        output_dir = generation_config.get("output_dir", "output/sql")
        # 需要从 db_domains 获取 db_name 来拼路径，这里直接扫描 output_dir
        output_path = _resolve_path(output_dir, project_root)
        pair_files = list(Path(output_path).glob("qs_*_pair.json"))
        if not pair_files:
            click.echo(f"未找到 pair 文件: {output_path}/qs_*_pair.json", err=True)
            raise click.Abort()
        if len(pair_files) > 1:
            click.echo(f"发现多个 pair 文件，请用 --input 指定:")
            for pf in pair_files:
                click.echo(f"  {pf}")
            raise click.Abort()
        input_file = str(pair_files[0])

    click.echo(f"校验文件: {input_file}")

    # 初始化 DatabaseConnector
    from metaweave.core.metadata.connector import DatabaseConnector

    db_config = main_config.get("database", {})
    connector = DatabaseConnector(db_config)

    # 可选：初始化 LLM 修复
    enable_repair = (
        enable_sql_repair
        if enable_sql_repair is not None
        else validation_config.get("enable_sql_repair", False)
    )
    llm_service = None
    if enable_repair:
        from metaweave.services.llm_service import LLMService
        from metaweave.services.llm_config_resolver import resolve_module_llm_config

        llm_config = resolve_module_llm_config(main_config, "sql_rag.llm")
        llm_service = LLMService(llm_config)

    # 解析 MD 和 REL 目录（修复时提供上下文）
    output_config = main_config.get("output", {})
    md_dir = str(_resolve_path(
        output_config.get("markdown_directory", "output/md"), project_root
    ))
    rel_dir = str(_resolve_path(
        output_config.get("rel_directory", "output/rel"), project_root
    ))

    # 创建校验器
    from metaweave.core.sql_rag.validator import SQLValidator

    validator = SQLValidator(
        connector=connector,
        config=validation_config,
        llm_service=llm_service,
        md_dir=md_dir,
        rel_dir=rel_dir,
    )

    # 执行校验
    click.echo("开始校验 SQL...")
    stats = validator.validate_file(
        input_file=input_file,
        enable_repair=enable_repair,
    )

    click.echo(f"校验完成:")
    click.echo(f"  总数: {stats['total']}")
    click.echo(f"  原始有效: {stats['valid']}, 无效: {stats['invalid']}")
    click.echo(f"  原始有效率: {stats['success_rate']:.1f}%")

    rs = stats["repair_stats"]
    if rs["attempted"] > 0:
        click.echo(f"  修复尝试: {rs['attempted']}, 成功: {rs['successful']}, 失败: {rs['failed']}")
        final_valid = stats["valid"] + rs["successful"]
        final_rate = final_valid / stats["total"] * 100 if stats["total"] else 0
        click.echo(f"  修复后有效: {final_valid}, 有效率: {final_rate:.1f}%")

    ras = stats["repair_apply_stats"]
    if ras["modified"] > 0 or ras["deleted"] > 0:
        click.echo(
            f"  修复回写: 替换 {ras['modified']} 条, 删除 {ras['deleted']} 条"
        )

    click.echo(f"  耗时: {stats['total_time']:.2f}s")


@sql_rag_command.command()
@click.option(
    "--config", "-c",
    type=click.Path(exists=True),
    default="configs/metadata_config.yaml",
    show_default=True,
    help="主配置文件路径（metadata_config.yaml）",
)
@click.option(
    "--input", "-i", "input_file",
    type=click.Path(exists=True),
    default=None,
    help="指定输入文件（覆盖配置中的 input_file）",
)
@click.option(
    "--clean", is_flag=True,
    help="加载前清空目标 Milvus Collection",
)
@click.option("--debug", is_flag=True, help="启用调试模式")
def load(config: str, input_file: Optional[str], clean: bool, debug: bool):
    """加载 Question-SQL 到 Milvus"""
    if debug:
        logging.getLogger("metaweave").setLevel(logging.DEBUG)

    set_current_step("sql")
    project_root = get_project_root()

    # 加载主配置
    main_config = _load_main_config(config, project_root)
    loader_config = main_config.get("loaders", {})
    # 保留 metadata_config_file 引用
    loader_config["metadata_config_file"] = str(_resolve_path(config, project_root))

    # CLI --input 优先；否则动态推断
    if input_file:
        if "sql_loader" not in loader_config:
            loader_config["sql_loader"] = {}
        loader_config["sql_loader"]["input_file"] = input_file
    elif not loader_config.get("sql_loader", {}).get("input_file"):
        # 从 database.database 动态拼出路径
        db_name = main_config.get("database", {}).get("database", "")
        if db_name:
            sql_output_dir = main_config.get("sql_rag", {}).get(
                "generation", {}
            ).get("output_dir", "output/sql")
            inferred_path = str(
                _resolve_path(sql_output_dir, project_root) / f"qs_{db_name}_pair.json"
            )
            if "sql_loader" not in loader_config:
                loader_config["sql_loader"] = {}
            loader_config["sql_loader"]["input_file"] = inferred_path
            click.echo(f"自动推断输入文件: {inferred_path}")

    # 创建加载器
    from metaweave.core.loaders.factory import LoaderFactory

    loader = LoaderFactory.create("sql", loader_config)

    # 执行加载
    click.echo("开始加载 SQL Example 到 Milvus...")
    if not loader.validate():
        click.echo("验证失败，请检查配置和依赖服务", err=True)
        raise click.Abort()

    result = loader.load(clean=clean)

    if result.get("success"):
        click.echo(f"加载完成: {result.get('message', '')}")
        click.echo(f"  加载: {result.get('loaded', 0)} 条")
        click.echo(f"  跳过: {result.get('skipped', 0)} 条")
        click.echo(f"  耗时: {result.get('execution_time', 0):.2f}s")
    else:
        click.echo(f"加载失败: {result.get('message', '未知错误')}", err=True)
        raise click.Abort()


@sql_rag_command.command(name="run-all")
@click.option(
    "--config", "-c",
    type=click.Path(exists=True),
    default="configs/metadata_config.yaml",
    show_default=True,
    help="主配置文件路径（metadata_config.yaml）",
)
@click.option(
    "--domains-config",
    type=click.Path(exists=True),
    default="configs/db_domains.yaml",
    show_default=True,
    help="db_domains.yaml 主题域配置路径",
)
@click.option(
    "--md-dir",
    type=click.Path(exists=True),
    default="output/md",
    show_default=True,
    help="Markdown 表结构目录",
)
@click.option(
    "--clean", is_flag=True,
    help="生成前清理当前库旧样例文件，并在加载前清空目标 Milvus Collection",
)
@click.option("--debug", is_flag=True, help="启用调试模式")
def run_all(
    config: str,
    domains_config: str,
    md_dir: str,
    clean: bool,
    debug: bool,
):
    """一键执行：生成 -> 校验 -> 加载"""
    if debug:
        logging.getLogger("metaweave").setLevel(logging.DEBUG)

    project_root = get_project_root()

    # 加载主配置
    main_config = _load_main_config(config, project_root)
    sql_rag_cfg = main_config.get("sql_rag", {})

    # === 阶段 1: 生成 ===
    set_current_step("sql-rag-generate")
    click.echo("=" * 50)
    click.echo("阶段 1: 生成 Question-SQL")
    click.echo("=" * 50)

    from metaweave.services.llm_service import LLMService
    from metaweave.services.llm_config_resolver import resolve_module_llm_config

    llm_config = resolve_module_llm_config(main_config, "sql_rag.llm")
    llm_service = LLMService(llm_config)

    from metaweave.core.sql_rag.generator import QuestionSQLGenerator

    generation_config = sql_rag_cfg.get("generation", {})
    generator = QuestionSQLGenerator(llm_service, generation_config)

    domains_path = _resolve_path(domains_config, project_root)
    md_dir_path = _resolve_path(md_dir, project_root)

    if clean:
        import yaml
        with open(domains_path, "r", encoding="utf-8") as f:
            domains_cfg = yaml.safe_load(f)
        db_name = domains_cfg.get("database", {}).get("name", "unknown")
        generator.clean_output(db_name)
        click.echo(f"已清理 {db_name} 的旧样例文件")

    gen_result = generator.generate(
        domains_config_path=str(domains_path),
        md_dir=str(md_dir_path),
    )

    if not gen_result.success:
        click.echo("生成失败，终止流程", err=True)
        raise click.Abort()

    click.echo(f"生成完成: {gen_result.total_generated} 条")

    # === 阶段 2: 校验 ===
    set_current_step("sql-rag-validate")
    click.echo("")
    click.echo("=" * 50)
    click.echo("阶段 2: SQL EXPLAIN 校验")
    click.echo("=" * 50)

    from metaweave.core.metadata.connector import DatabaseConnector
    from metaweave.core.sql_rag.validator import SQLValidator

    db_config = main_config.get("database", {})
    connector = DatabaseConnector(db_config)

    validation_config = sql_rag_cfg.get("validation", {})
    enable_repair = validation_config.get("enable_sql_repair", False)

    # 修复时需要 LLM
    repair_llm = llm_service if enable_repair else None

    # 解析 MD 和 REL 目录（修复时提供上下文）
    output_config = main_config.get("output", {})
    md_dir_resolved = str(_resolve_path(
        output_config.get("markdown_directory", "output/md"), project_root
    ))
    rel_dir_resolved = str(_resolve_path(
        output_config.get("rel_directory", "output/rel"), project_root
    ))

    validator = SQLValidator(
        connector=connector,
        config=validation_config,
        llm_service=repair_llm,
        md_dir=md_dir_resolved,
        rel_dir=rel_dir_resolved,
    )

    stats = validator.validate_file(
        input_file=gen_result.output_file,
        enable_repair=enable_repair,
    )

    click.echo("校验完成:")
    click.echo(f"  总数: {stats['total']}")
    click.echo(f"  原始有效: {stats['valid']}, 无效: {stats['invalid']}")
    click.echo(f"  原始有效率: {stats['success_rate']:.1f}%")

    rs = stats["repair_stats"]
    final_valid = stats["valid"]
    final_rate = stats["success_rate"]
    if rs["attempted"] > 0:
        click.echo(
            f"  修复尝试: {rs['attempted']}, 成功: {rs['successful']}, 失败: {rs['failed']}"
        )
        final_valid = stats["valid"] + rs["successful"]
        final_rate = final_valid / stats["total"] * 100 if stats["total"] else 0
        click.echo(f"  修复后有效: {final_valid}, 有效率: {final_rate:.1f}%")

    ras = stats["repair_apply_stats"]
    if ras["modified"] > 0 or ras["deleted"] > 0:
        click.echo(
            f"  修复回写: 替换 {ras['modified']} 条, 删除 {ras['deleted']} 条"
        )

    # === 阶段 3: 加载 ===
    set_current_step("sql")
    click.echo("")
    click.echo("=" * 50)
    click.echo("阶段 3: 加载到 Milvus")
    click.echo("=" * 50)

    loader_config = main_config.get("loaders", {})
    loader_config["metadata_config_file"] = str(_resolve_path(config, project_root))

    # 将生成的文件路径注入 loader 配置
    if "sql_loader" not in loader_config:
        loader_config["sql_loader"] = {}
    loader_config["sql_loader"]["input_file"] = gen_result.output_file

    from metaweave.core.loaders.factory import LoaderFactory

    loader = LoaderFactory.create("sql", loader_config)

    if not loader.validate():
        click.echo("Loader 验证失败", err=True)
        raise click.Abort()

    result = loader.load(clean=clean)

    if result.get("success"):
        click.echo(f"加载完成: {result.get('message', '')}")
    else:
        click.echo(f"加载失败: {result.get('message', '')}", err=True)
        raise click.Abort()

    # 汇总
    click.echo("")
    click.echo("=" * 50)
    click.echo("全流程完成")
    click.echo("=" * 50)
    click.echo(f"  生成: {gen_result.total_generated} 条")
    if rs["attempted"] > 0:
        click.echo(
            f"  校验: 修复后有效 {final_valid}/{stats['total']} ({final_rate:.1f}%)"
        )
    else:
        click.echo(f"  校验: 原始有效 {stats['valid']}/{stats['total']}")
    click.echo(f"  加载: {result.get('loaded', 0)} 条")


def _resolve_path(path_str: str, project_root: Path) -> Path:
    """解析路径：相对路径基于项目根目录"""
    p = Path(path_str)
    if not p.is_absolute():
        p = project_root / p
    return p
