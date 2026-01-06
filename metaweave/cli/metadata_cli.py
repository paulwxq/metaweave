"""元数据生成 CLI 命令"""

import copy
import click
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional
import yaml

from metaweave.core.metadata.generator import MetadataGenerator
from metaweave.utils.file_utils import get_project_root, clear_dir_contents
from metaweave.utils.logger import set_current_step

logger = logging.getLogger("metaweave.cli")


@click.command(name="metadata")
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    required=True,
    help="配置文件路径"
)
@click.option(
    "--schemas",
    "-s",
    type=str,
    help="要处理的 schema 列表（逗号分隔）"
)
@click.option(
    "--tables",
    "-t",
    type=str,
    help="要处理的表名列表（逗号分隔）"
)
@click.option(
    "--incremental",
    "-i",
    is_flag=True,
    help="增量更新模式（仅处理变更的表）"
)
@click.option(
    "--max-workers",
    "-w",
    type=int,
    default=4,
    help="最大并发数（默认: 4）"
)
@click.option(
    "--clean",
    is_flag=True,
    default=False,
    help="在写入前清空该 step 的输出目录"
)
@click.option(
    "--step",
    type=click.Choice(["ddl", "json", "json_llm", "cql", "cql_llm", "md", "rel", "rel_llm", "all", "all_llm"], case_sensitive=False),
    default="all",
    show_default=True,
    help="指定要执行的步骤：ddl/json/json_llm/cql/cql_llm/md/rel/rel_llm/all/all_llm"
)
@click.option(
    "--domain",
    type=str,
    default=None,
    flag_value="all",
    help="启用 domain 功能。不传值或传 'all' 表示使用所有 domain；传 'A,B' 表示只使用指定 domain"
)
@click.option(
    "--domains-config",
    type=click.Path(exists=False),
    default="configs/db_domains.yaml",
    help="业务主题配置文件路径（默认：configs/db_domains.yaml）"
)
@click.option(
    "--generate-domains",
    is_flag=True,
    default=False,
    help="根据 db_domains.yaml 中的 database.description 自动生成 domains 列表"
)
@click.option(
    "--cross-domain",
    is_flag=True,
    default=False,
    help="是否包含跨域关系。可与 --domain 一起使用，也可单独使用（只生成跨域关系）"
)
@click.option(
    "--md-context",
    is_flag=True,
    default=False,
    help="生成 domains 时附加 md 目录摘要"
)
@click.option(
    "--md-context-dir",
    type=click.Path(exists=False),
    default="output/md",
    help="md 摘要目录（默认：output/md）"
)
@click.option(
    "--md-context-mode",
    type=click.Choice(["name", "name_comment", "full"], case_sensitive=False),
    default="name_comment",
    show_default=True,
    help="md 摘要模式：name 仅表名；name_comment 表名+首行；full 全文"
)
@click.option(
    "--md-context-limit",
    type=int,
    default=100,
    show_default=True,
    help="md 文件数量上限，超出截断"
)
def metadata_command(
    config: str,
    schemas: str,
    tables: str,
    incremental: bool,
    max_workers: int,
    clean: bool,
    step: str,
    domain: Optional[str],
    domains_config: str,
    generate_domains: bool,
    cross_domain: bool,
    md_context: bool,
    md_context_dir: str,
    md_context_mode: str,
    md_context_limit: int,
):
    """生成数据库元数据
    
    从 PostgreSQL 数据库中提取元数据、生成注释、识别逻辑主键，
    并输出为 DDL、Markdown、JSON 格式。
    
    示例:
    
        metaweave metadata --config configs/metadata_config.yaml
        
        metaweave metadata -c config.yaml --schemas public,myschema
        
        metaweave metadata -c config.yaml --tables users,orders --max-workers 8
    """
    try:
        set_current_step((step or "all").lower())

        def _load_yaml(path: Path) -> Dict:
            if not path.exists():
                return {}
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}

        def _parse_domain_filter(domain_value: Optional[str]) -> Optional[List[str]]:
            if not domain_value:
                return None
            lower = domain_value.lower()
            if lower == "all":
                return ["all"]
            return [d.strip() for d in domain_value.split(",") if d.strip()]

        # 解析配置文件路径
        config_path = Path(config)
        if not config_path.is_absolute():
            config_path = get_project_root() / config_path

        click.echo(f"📋 加载配置: {config_path}")

        step_lower = (step or "all").lower()

        def _ensure_in_project_root(path: Path) -> Path:
            project_root = get_project_root().resolve()
            resolved = path.resolve()
            if (resolved != project_root) and (project_root not in resolved.parents):
                raise click.UsageError(f"❌ --clean 输出目录不在项目根目录内: {resolved}")
            return resolved

        def _clean_step_output_dir(step_name: str, loaded_config: Dict) -> None:
            """清空指定步骤的输出目录

            Args:
                step_name: 步骤名称（ddl/json/json_llm/md/rel/rel_llm/cql/cql_llm）
                loaded_config: 已加载的配置字典

            Raises:
                click.UsageError: 不支持的步骤或输出目录不在项目根目录内
            """
            step_name = (step_name or "").lower()
            output_config = loaded_config.get("output", {}) or {}

            # 统一以 cwd 解析相对路径，保持与现有各模块行为一致
            def _resolve_dir(path_str: str) -> Path:
                p = Path(path_str)
                if not p.is_absolute():
                    p = Path(os.getcwd()) / p
                return _ensure_in_project_root(p)

            output_dir = _resolve_dir(str(output_config.get("output_dir", "output")))

            if step_name == "ddl":
                target_dir = output_dir / "ddl"
            elif step_name in {"json", "json_llm"}:
                target_dir = output_dir / "json"
            elif step_name == "md":
                target_dir = output_dir / "md"
            elif step_name in {"rel", "rel_llm"}:
                target_dir = _resolve_dir(str(output_config.get("rel_directory", "output/rel")))
            elif step_name in {"cql", "cql_llm"}:
                target_dir = _resolve_dir(str(output_config.get("cql_directory", "output/cql")))
            else:
                raise click.UsageError(f"❌ --clean 不支持的 step: {step_name}")

            clear_dir_contents(target_dir)
            logger.debug(f"🧹 已清空输出目录: {target_dir}")

        def _log_step_failure(step_name: str, message: str, errors: Optional[List[str]] = None):
            """记录步骤失败日志（不抛出异常）

            Args:
                step_name: 当前失败的步骤名
                message: 失败原因摘要
                errors: 可选的错误列表（最多输出前 10 条）
            """
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

        def _abort_step(step_name: str, message: str, errors: Optional[List[str]] = None):
            """以 fail-fast 方式终止 orchestrator 并输出错误摘要（仅供单步骤使用）

            Args:
                step_name: 当前失败的步骤名
                message: 失败原因摘要
                errors: 可选的错误列表（最多输出前 10 条）

            Raises:
                click.Abort: 终止 CLI 执行（返回非 0）
            """
            _log_step_failure(step_name, message, errors)
            raise click.Abort()

        # 参数校验
        if generate_domains and domain:
            raise click.UsageError("--generate-domains 和 --domain 不能同时使用，请分两步执行")

        domains_config_path = Path(domains_config)
        if not domains_config_path.is_absolute():
            domains_config_path = get_project_root() / domains_config_path
        db_domains_config: Optional[Dict] = None

        if domain or cross_domain:
            if not domains_config_path.exists():
                raise click.UsageError(f"错误：{domains_config} 文件不存在，无法使用 --domain/--cross-domain")
            db_domains_config = _load_yaml(domains_config_path)
            domains_list = db_domains_config.get("domains", [])
            if not domains_list:
                raise click.UsageError(f"错误：{domains_config} 中 domains 列表为空，请先执行 --generate-domains")

        if generate_domains:
            if not domains_config_path.exists():
                raise click.UsageError(f"错误：{domains_config} 文件不存在，请先创建并填写 database.description")
            db_domains_config = _load_yaml(domains_config_path)
            description = db_domains_config.get("database", {}).get("description", "")
            if not description or not description.strip():
                raise click.UsageError("错误：database.description 为空，无法生成 domains 列表")

        # generate-domains 可独立执行（不依赖 step）
        if generate_domains and step != "json_llm":
            from metaweave.core.metadata.domain_generator import DomainGenerator
            from services.config_loader import load_config

            config = load_config(config_path)
            md_dir = Path(md_context_dir)
            if not md_dir.is_absolute():
                md_dir = get_project_root() / md_dir

            generator = DomainGenerator(
                config=config,
                yaml_path=str(domains_config_path),
                md_context=md_context,
                md_context_dir=str(md_dir),
                md_context_mode=md_context_mode,
                md_context_limit=md_context_limit,
            )
            domains = generator.generate_from_description()
            generator.write_to_yaml(domains)
            click.echo(f"✅ 已生成 {len(domains)} 个 domain 并写入 {domains_config_path}")
            return

        domain_filter = _parse_domain_filter(domain)

        # Step: all / all_llm - 串行调度多个步骤（fail-fast）
        if step_lower in {"all", "all_llm"}:
            from services.config_loader import load_config

            loaded_config = load_config(config_path)

            schemas_list = [s.strip() for s in (schemas or "").split(",") if s.strip()] or None
            tables_list = [t.strip() for t in (tables or "").split(",") if t.strip()] or None

            if step_lower == "all":
                steps = ["ddl", "md", "json", "rel", "cql"]
            else:
                steps = ["ddl", "md", "json_llm", "rel_llm", "cql"]

            # 明确设置主上下文并记录启动日志
            parent_step = step_lower
            set_current_step(parent_step)
            
            logger.info("🚀 开始全流程执行: %s", parent_step)
            logger.info("🧭 调度顺序: %s", " -> ".join(steps))

            click.echo(f"🧱 执行步骤: {step_lower}")
            click.echo(f"🧭 调度顺序: {' -> '.join(steps)}")
            click.echo(f"⚙️  并发数: {max_workers}")
            click.echo("")

            try:
                for child_step in steps:
                    # --- 阶段 1: 启动前 (Parent Context) ---
                    set_current_step(parent_step)
                    logger.info("▶️  正在启动子步骤: %s", child_step)

                    click.echo("")
                    click.echo("=" * 60)
                    click.echo(f"▶️  开始步骤: {child_step}")
                    click.echo("=" * 60)

                    # --- 阶段 2: 执行子步骤 (Child Context) ---
                    set_current_step(child_step)

                    step_success = False
                    step_error_msg = ""
                    step_errors = []

                    try:
                        # 1. 依赖检查
                        if child_step == "md":
                            output_dir = Path(loaded_config.get("output", {}).get("output_dir", "output"))
                            if not output_dir.is_absolute():
                                output_dir = get_project_root() / output_dir
                            ddl_dir = output_dir / "ddl"
                            ddl_files = list(ddl_dir.glob("*.sql")) if ddl_dir.exists() else []
                            if not ddl_files:
                                raise ValueError(f"DDL 目录为空: {ddl_dir}")

                        # 2. 清理操作
                        if clean:
                            logger.debug(f"正在清理输出目录: {child_step}")
                            _clean_step_output_dir(child_step, loaded_config)

                        # 3. 执行子步骤
                        if child_step in {"ddl", "json", "md"}:
                            generator = MetadataGenerator(config_path)
                            result = generator.generate(
                                schemas=schemas_list,
                                tables=tables_list,
                                incremental=incremental,
                                max_workers=max_workers,
                                step=child_step,
                            )

                            if (not result.success) or (result.failed_tables > 0):
                                step_error_msg = f"处理失败: 成功 {result.processed_tables}，失败 {result.failed_tables}"
                                step_errors = result.errors
                            else:
                                step_success = True

                        elif child_step == "json_llm":
                            from metaweave.core.metadata.json_llm_enhancer import JsonLlmEnhancer
                            
                            click.echo("📊 阶段 1/2: 生成全量 JSON（--step json）...")
                            generator = MetadataGenerator(config_path)
                            config_for_llm = generator.config

                            result_a = generator.generate(
                                schemas=schemas_list,
                                tables=tables_list,
                                incremental=incremental,
                                max_workers=max_workers,
                                step="json",
                            )

                            if (not result_a.success) or (result_a.failed_tables > 0):
                                step_error_msg = "阶段 A (--step json) 失败"
                                step_errors = result_a.errors
                            else:
                                json_dir = (generator.formatter.output_dir / "json").resolve()
                                json_files = [
                                    Path(p)
                                    for p in result_a.output_files
                                    if Path(p).suffix == ".json" and Path(p).resolve().parent == json_dir
                                ]

                                if not json_files:
                                    step_error_msg = "阶段 A 未生成任何 JSON 文件"
                                else:
                                    cli_config = copy.deepcopy(config_for_llm)
                                    if "llm" in cli_config and "langchain_config" in cli_config["llm"]:
                                        cli_config["llm"]["langchain_config"]["use_async"] = False

                                    click.echo("🤖 阶段 2/2: LLM 增强处理（原地写回 output/json）...")
                                    enhancer = JsonLlmEnhancer(cli_config)
                                    enhanced_count = enhancer.enhance_json_files(json_files)
                                    step_success = True

                        elif child_step == "rel":
                            from metaweave.core.relationships.pipeline import RelationshipDiscoveryPipeline

                            pipeline = RelationshipDiscoveryPipeline(config_path)
                            result = pipeline.discover()
                            if not result.success:
                                step_error_msg = "关系发现失败"
                                step_errors = result.errors
                            else:
                                step_success = True

                        elif child_step == "rel_llm":
                            from metaweave.core.relationships.llm_relationship_discovery import LLMRelationshipDiscovery
                            from metaweave.core.relationships.writer import RelationshipWriter
                            from metaweave.core.metadata.connector import DatabaseConnector

                            connector = DatabaseConnector(loaded_config.get("database", {}))
                            try:
                                discovery = LLMRelationshipDiscovery(
                                    config=loaded_config,
                                    connector=connector,
                                    domain_filter=domain,
                                    cross_domain=cross_domain,
                                    db_domains_config=db_domains_config,
                                )

                                if not discovery.json_dir.exists():
                                    raise FileNotFoundError(f"json 目录不存在: {discovery.json_dir}")

                                relations, rejected_count, extra_statistics = discovery.discover()

                                writer = RelationshipWriter(loaded_config)
                                output_files = writer.write_results(
                                    relations=relations,
                                    suppressed=[],
                                    config=loaded_config,
                                    tables=discovery.tables,
                                    generated_by="rel_llm",
                                    extra_statistics=extra_statistics,
                                )
                                for f in output_files:
                                    logger.info("rel_llm 输出文件: %s", f)
                                step_success = True
                            finally:
                                connector.close()

                        elif child_step == "cql":
                            from metaweave.core.cql_generator.generator import CQLGenerator

                            generator = CQLGenerator(config_path)
                            result = generator.generate(step_name="cql")
                            if not result.success:
                                step_error_msg = "CQL 生成失败"
                                step_errors = result.errors
                            else:
                                step_success = True

                        else:
                            raise ValueError(f"未知步骤: {child_step}")

                    except Exception as e:
                        # 捕获异常：保留完整堆栈到 child.log
                        logger.error("子步骤内部异常: %s", e, exc_info=True)
                        step_success = False
                        step_error_msg = str(e)

                    # --- 阶段 3: 执行后 (Parent Context) ---
                    set_current_step(parent_step)

                    if not step_success:
                        logger.error("❌ 子步骤失败: %s. 原因: %s", child_step, step_error_msg)
                        click.echo(f"❌ {child_step} 失败: {step_error_msg}", err=True)
                        
                        if step_errors:
                            for err in step_errors[:10]:
                                logger.error("  - %s", err)
                                click.echo(f"  - {err}", err=True)
                            if len(step_errors) > 10:
                                msg = f"  ... 还有 {len(step_errors) - 10} 个错误"
                                logger.error(msg)
                                click.echo(msg, err=True)
                                
                        logger.error("⛔ 全流程终止")
                        raise click.Abort()
                    else:
                        logger.info("✅ 子步骤完成: %s", child_step)
                        click.echo(f"✅ {child_step} 完成")

                logger.info("✨ 全流程执行成功完成")
                click.echo("")
                click.echo(f"✨ {parent_step} 处理完成！")
                return

            except click.Abort:
                set_current_step(parent_step)
                logger.error("🛑 流程被中止")
                raise
            except Exception as e:
                set_current_step(parent_step)
                logger.error("❌ 全局未捕获异常: %s", e, exc_info=True)
                click.echo(f"❌ 未预期错误: {e}", err=True)
                raise click.Abort()

        # Step: json_llm - 基于 json 的 LLM 增强（两阶段串行）
        if step == "json_llm":
            from metaweave.core.metadata.json_llm_enhancer import JsonLlmEnhancer
            from metaweave.core.metadata.domain_generator import DomainGenerator
            from services.config_loader import load_config

            click.echo("📦 开始 LLM 增强处理（json_llm）...")
            click.echo("   ├─ 阶段 1/2: 生成全量 JSON（--step json）")
            click.echo("   └─ 阶段 2/2: LLM 增强（分类覆盖 + 注释补全）")
            click.echo("")

            # generate-domains 单独执行
            if generate_domains:
                config = load_config(config_path)
                md_dir = Path(md_context_dir)
                if not md_dir.is_absolute():
                    md_dir = get_project_root() / md_dir
                generator = DomainGenerator(
                    config=config,
                    yaml_path=str(domains_config_path),
                    md_context=md_context,
                    md_context_dir=str(md_dir),
                    md_context_mode=md_context_mode,
                    md_context_limit=md_context_limit,
                )
                domains = generator.generate_from_description()
                generator.write_to_yaml(domains)
                click.echo(f"✅ 已生成 {len(domains)} 个 domain 并写入 {domains_config_path}")
                return

            # ====== 阶段 A：生成全量 JSON（失败则直接退出）======
            click.echo("📊 阶段 1/2: 生成全量 JSON（--step json）...")

            # 注：MetadataGenerator 构造函数接受 config_path，并在内部加载/解析配置（含环境变量替换）
            generator = MetadataGenerator(config_path)
            config = generator.config  # 复用已解析配置（避免重复加载/环境变量替换差异）

            if clean:
                _clean_step_output_dir("json_llm", config)

            # 透传 CLI 参数（否则 json_llm 会忽略 schemas/tables/max_workers 等过滤条件）
            schemas_list = [s.strip() for s in (schemas or "").split(",") if s.strip()] or None
            tables_list = [t.strip() for t in (tables or "").split(",") if t.strip()] or None

            result_a = generator.generate(
                schemas=schemas_list,
                tables=tables_list,
                incremental=incremental,
                max_workers=max_workers,
                step="json",
            )

            if (not result_a.success) or result_a.failed_tables > 0:
                # 阶段A失败：打印错误并退出（阶段B不执行）
                error_msg = "阶段 A (--step json) 失败，退出。"
                if result_a.errors:
                    error_msg += "\n错误详情:\n" + "\n".join(f"  - {e}" for e in result_a.errors[:10])
                raise click.ClickException(error_msg)

            click.echo(f"✅ 阶段 1 完成：成功处理 {result_a.processed_tables} 张表")
            click.echo("")

            # ====== 阶段 B：LLM 增强 ======
            click.echo("🤖 阶段 2/2: LLM 增强处理（原地写回 output/json）...")

            # 阶段B只处理本次阶段A产出的 JSON 文件，且限定在 output/json 目录下，避免误包含其他 JSON
            json_dir = (generator.formatter.output_dir / "json").resolve()
            json_files = [
                Path(p)
                for p in result_a.output_files
                if Path(p).suffix == ".json" and Path(p).resolve().parent == json_dir
            ]

            if not json_files:
                click.echo("⚠️  阶段 A 未生成任何 JSON 文件，跳过阶段 B")
                click.echo("✨ json_llm 处理完成（仅执行了阶段 A）")
                return

            # 强制 CLI 使用同步模式（CLI 工具不需要异步复杂性）
            cli_config = copy.deepcopy(config)
            if "llm" in cli_config and "langchain_config" in cli_config["llm"]:
                cli_config["llm"]["langchain_config"]["use_async"] = False

            # 初始化增强器（不查库，只基于 JSON 调用 LLM）
            enhancer = JsonLlmEnhancer(cli_config)

            # 调用增强方法（同步模式保证返回 int）
            enhanced_count = enhancer.enhance_json_files(json_files)

            # 显示结果
            click.echo("")
            click.echo("=" * 60)
            click.echo("📊 json_llm 处理结果")
            click.echo("=" * 60)
            click.echo(f"✅ 阶段 A (json): 成功处理 {result_a.processed_tables} 张表")
            click.echo(f"✅ 阶段 B (LLM 增强): 增强 {enhanced_count} 个文件")
            click.echo(f"📁 输出目录: {json_dir}")
            click.echo("=" * 60)
            click.echo("✨ json_llm 处理完成！")

            return

        # Step: rel_llm - LLM 辅助关系发现
        if step == "rel_llm":
            from metaweave.core.relationships.llm_relationship_discovery import LLMRelationshipDiscovery
            from metaweave.core.relationships.writer import RelationshipWriter
            from metaweave.core.metadata.connector import DatabaseConnector
            from services.config_loader import load_config

            click.echo("🤖 开始 LLM 辅助关系发现（rel_llm）...")
            click.echo("")

            # 加载配置
            config = load_config(config_path)

            if clean:
                _clean_step_output_dir("rel_llm", config)

            # 初始化连接器
            connector = DatabaseConnector(config.get("database", {}))

            try:
                # 初始化发现器
                discovery = LLMRelationshipDiscovery(
                    config=config,
                    connector=connector,
                    domain_filter=domain,
                    cross_domain=cross_domain,
                    db_domains_config=db_domains_config
                )

                # 检查 json 目录
                if not discovery.json_dir.exists():
                    raise FileNotFoundError(
                        f"json 目录不存在: {discovery.json_dir}\n"
                        f"请先执行 --step json 生成表元数据 JSON"
                    )

                # 发现关系
                relations, rejected_count, extra_statistics = discovery.discover()

                # 使用 RelationshipWriter 输出结果
                writer = RelationshipWriter(config)
                output_files = writer.write_results(
                    relations=relations,
                    suppressed=[],  # LLM 流程没有 suppressed 关系
                    config=config,
                    tables=discovery.tables,  # 传递表元数据（discovery 已缓存）
                    generated_by="rel_llm",  # 标识 LLM 辅助生成
                    extra_statistics=extra_statistics
                )

                # 显示结果
                click.echo("")
                click.echo("=" * 60)
                click.echo("📊 LLM 辅助关系发现结果")
                click.echo("=" * 60)
                total_relations = len(relations)
                llm_assisted = extra_statistics.get("llm_assisted_relationships", 0)
                fk_relations = total_relations - llm_assisted
                click.echo(f"✅ 总关系数: {total_relations} 个")
                click.echo(f"  - 物理外键: {fk_relations}")
                click.echo(f"  - LLM 推断: {llm_assisted}")
                if rejected_count > 0:
                    click.echo(f"  - 低置信度拒绝: {rejected_count}")
                click.echo(f"📁 输出文件:")
                for output_file in output_files:
                    click.echo(f"  - {output_file}")
                click.echo("=" * 60)
                click.echo("✨ LLM 辅助关系发现完成！")

            finally:
                # 关闭数据库连接（与 rel pipeline 保持一致）
                connector.close()

            return

        # Step: cql_llm - CQL 生成（等同于 cql）
        if step == "cql_llm":
            from metaweave.core.cql_generator.generator import CQLGenerator

            click.echo("🔧 开始生成 Neo4j CQL...")
            click.echo("")

            generator = CQLGenerator(config_path)

            if clean:
                _clean_step_output_dir("cql_llm", generator.config)

            # ✅ 检测废弃配置（帮助用户平滑过渡）
            if generator.config.get("output", {}).get("json_llm_directory"):
                logger.warning(
                    "⚠️ 配置项 'json_llm_directory' 已废弃，"
                    "cql_llm 现在使用 'json_directory'，与 cql 行为一致"
                )

            # ✅ 统一使用 json_directory（不再读取 json_llm_directory）
            # generator.json_dir 默认已指向 output.json_directory
            logger.info(f"使用 cql_llm 命令（功能等同于 cql）")
            logger.info(f"使用 JSON 目录: {generator.json_dir}")

            # ✅ 传递命令名称（用于元数据生成）
            result = generator.generate(step_name="cql_llm")

            # 显示结果统计
            click.echo("")
            click.echo("=" * 60)
            click.echo("📊 CQL 生成结果统计")
            click.echo("=" * 60)
            click.echo(f"✅ 表节点: {result.tables_count} 个")
            click.echo(f"✅ 列节点: {result.columns_count} 个")
            click.echo(f"✅ HAS_COLUMN 关系: {result.has_column_count} 个")
            click.echo(f"✅ JOIN_ON 关系: {result.relationships_count} 个")
            click.echo(f"✅ 边总数: {result.has_column_count + result.relationships_count} 个")
            click.echo(f"📁 输出文件: {len(result.output_files)} 个")

            for file_path in result.output_files:
                click.echo(f"  - {Path(file_path).name}")

            if result.errors:
                click.echo(f"\n⚠️  错误列表:")
                for error in result.errors[:5]:
                    click.echo(f"  - {error}", err=True)
                if len(result.errors) > 5:
                    click.echo(f"  ... 还有 {len(result.errors) - 5} 个错误", err=True)

            click.echo("=" * 60)

            if result.success:
                click.echo("✨ CQL 生成完成！")
            else:
                click.echo("⚠️  CQL 生成完成，但存在错误", err=True)
                raise click.Abort()

            return

        # Step 4: CQL 生成
        if step == "cql":
            from metaweave.core.cql_generator.generator import CQLGenerator

            click.echo("🔧 开始生成 Neo4j CQL...")
            click.echo("")

            generator = CQLGenerator(config_path)

            if clean:
                _clean_step_output_dir("cql", generator.config)

            # ✅ 传递命令名称（用于元数据生成）
            result = generator.generate(step_name="cql")

            # 显示结果统计
            click.echo("")
            click.echo("=" * 60)
            click.echo("📊 CQL 生成结果统计")
            click.echo("=" * 60)
            click.echo(f"✅ 表节点: {result.tables_count} 个")
            click.echo(f"✅ 列节点: {result.columns_count} 个")
            click.echo(f"✅ HAS_COLUMN 关系: {result.has_column_count} 个")
            click.echo(f"✅ JOIN_ON 关系: {result.relationships_count} 个")
            click.echo(f"✅ 边总数: {result.has_column_count + result.relationships_count} 个")
            click.echo(f"📁 输出文件: {len(result.output_files)} 个")

            for file_path in result.output_files:
                click.echo(f"  - {Path(file_path).name}")

            if result.errors:
                click.echo(f"\n⚠️  错误列表:")
                for error in result.errors[:5]:
                    click.echo(f"  - {error}", err=True)
                if len(result.errors) > 5:
                    click.echo(f"  ... 还有 {len(result.errors) - 5} 个错误", err=True)

            click.echo("=" * 60)

            if result.success:
                click.echo("✨ CQL 生成完成！")
            else:
                click.echo("⚠️  CQL 生成完成，但存在错误", err=True)
                raise click.Abort()

            return

        # Step 3: 关系发现
        if step == "rel":
            from metaweave.core.relationships.pipeline import RelationshipDiscoveryPipeline
            from services.config_loader import load_config

            click.echo("🔗 开始关系发现...")
            click.echo("")

            if clean:
                config = load_config(config_path)
                _clean_step_output_dir("rel", config)

            pipeline = RelationshipDiscoveryPipeline(config_path)
            result = pipeline.discover()

            # 显示结果统计
            click.echo("")
            click.echo("=" * 60)
            click.echo("📊 关系发现结果统计")
            click.echo("=" * 60)
            click.echo(f"✅ 发现关系: {result.total_relations} 个")
            click.echo(f"  - 外键直通: {result.foreign_key_relations}")
            click.echo(f"  - 推断关系: {result.inferred_relations}")
            click.echo(f"  - 高置信度: {result.high_confidence_count}")
            click.echo(f"  - 中置信度: {result.medium_confidence_count}")
            click.echo(f"  - 抑制数量: {result.suppressed_count}")
            click.echo(f"📁 输出文件: {len(result.output_files)} 个")

            if result.errors:
                click.echo(f"\n⚠️  错误列表:")
                for error in result.errors[:5]:
                    click.echo(f"  - {error}", err=True)
                if len(result.errors) > 5:
                    click.echo(f"  ... 还有 {len(result.errors) - 5} 个错误", err=True)

            click.echo("=" * 60)

            if result.success:
                click.echo("✨ 关系发现完成！")
            else:
                click.echo("⚠️  关系发现完成，但存在错误", err=True)
                raise click.Abort()

            return

        # ========== 新增：md 步骤依赖检查 ==========
        if step.lower() == "md":
            from services.config_loader import load_config

            # 加载配置获取真实的 output_dir
            loaded_config = load_config(config_path)
            output_dir = Path(loaded_config.get("output", {}).get("output_dir", "output"))
            if not output_dir.is_absolute():
                output_dir = get_project_root() / output_dir

            ddl_dir = output_dir / "ddl"

            if not ddl_dir.exists():
                raise click.UsageError(
                    f"❌ --step md 依赖 DDL 文件，但 DDL 目录不存在: {ddl_dir}\n"
                    f"请先执行: metaweave metadata --config {config} --step ddl"
                )

            # 检查是否有 DDL 文件（文件名格式：{database}.{schema}.{table}.sql）
            ddl_files = list(ddl_dir.glob("*.sql"))
            if not ddl_files:
                raise click.UsageError(
                    f"❌ --step md 依赖 DDL 文件，但 DDL 目录为空: {ddl_dir}\n"
                    f"请先执行: metaweave metadata --config {config} --step ddl"
                )

            click.echo(f"✅ 检测到 {len(ddl_files)} 个 DDL 文件，继续执行...")
        # ==========================================

        # 清理当前 step 输出目录（ddl/json/md）
        if clean and step_lower in {"ddl", "json", "md"}:
            from services.config_loader import load_config
            loaded_config = load_config(config_path)
            _clean_step_output_dir(step_lower, loaded_config)

        # 初始化生成器（Step 2）
        generator = MetadataGenerator(config_path)
        
        # 解析 schemas 和 tables
        schema_list = None
        if schemas:
            schema_list = [s.strip() for s in schemas.split(",")]
            click.echo(f"🎯 指定 Schema: {schema_list}")
        
        table_list = None
        if tables:
            table_list = [t.strip() for t in tables.split(",")]
            click.echo(f"🎯 指定表: {table_list}")
        
        if incremental:
            click.echo("🔄 增量更新模式")
        
        click.echo(f"⚙️  并发数: {max_workers}")
        click.echo(f"🧱 执行步骤: {step_lower}")
        click.echo("")
        
        # 执行生成
        click.echo("🚀 开始生成元数据...")
        result = generator.generate(
            schemas=schema_list,
            tables=table_list,
            incremental=incremental,
            max_workers=max_workers,
            step=step
        )
        
        # 显示结果
        click.echo("")
        click.echo("=" * 60)
        click.echo("📊 生成结果统计")
        click.echo("=" * 60)
        click.echo(f"✅ 成功处理: {result.processed_tables} 张表")
        
        if result.failed_tables > 0:
            click.echo(f"❌ 处理失败: {result.failed_tables} 张表", err=True)
        
        click.echo(f"💬 生成注释: {result.generated_comments} 个")
        click.echo(f"🔑 识别逻辑主键: {result.logical_keys_found} 个")
        click.echo(f"📁 输出文件: {len(result.output_files)} 个")
        
        if result.errors:
            click.echo(f"\n⚠️  错误列表:")
            for error in result.errors[:5]:
                click.echo(f"  - {error}", err=True)
            if len(result.errors) > 5:
                click.echo(f"  ... 还有 {len(result.errors) - 5} 个错误", err=True)
        
        click.echo("=" * 60)
        
        if result.success:
            click.echo("✨ 元数据生成完成！")
        else:
            click.echo("⚠️  元数据生成完成，但存在错误", err=True)
            raise click.Abort()
    
    except Exception as e:
        logger.error(f"元数据生成失败: {e}")
        click.echo(f"❌ 错误: {e}", err=True)
        raise click.Abort()
