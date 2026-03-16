# 57_pipeline_generate_load 详细设计

本文档是 `56_pipeline_generate_load最终规范` 的实施设计文档，定义新增 `pipeline` 命令组的代码结构、模块交互、复用策略及具体实现细节。

## 1. 整体改动范围

### 1.1 新增文件

| 文件 | 说明 |
|------|------|
| `metaweave/cli/pipeline_cli.py` | `pipeline` 命令组入口，包含 `generate` 和 `load` 两个子命令 |

### 1.2 修改文件

| 文件 | 改动说明 |
|------|---------|
| `metaweave/cli/main.py` | 注册 `pipeline` 命令组 |

### 1.3 不修改的文件

现有 `metadata_cli.py`、`loader_cli.py`、`sql_rag_cli.py`、`dim_config_cli.py` 保持不变。`pipeline` 命令是对现有能力的**编排层封装**，不改动底层模块的接口或行为。

## 2. CLI 命令结构设计

### 2.1 命令层级

```text
metaweave
├── metadata          （保留，单步执行）
├── load              （保留，单类型加载）
├── dim_config        （保留，独立工具）
├── sql-rag           （保留，独立工具）
└── pipeline          （新增）
    ├── generate      （新增）
    └── load          （新增）
```

### 2.2 main.py 注册

在 `main.py` 中新增：

```python
from metaweave.cli.pipeline_cli import pipeline_command

cli.add_command(pipeline_command)
```

### 2.3 pipeline_cli.py 结构

```python
@click.group(name="pipeline")
def pipeline_command():
    """统一编排命令：生成全部产物或加载到目标库"""
    pass

@pipeline_command.command(name="generate")
@click.option(...)
def pipeline_generate(...):
    ...

@pipeline_command.command(name="load")
@click.option(...)
def pipeline_load(...):
    ...
```

## 3. pipeline generate 详细设计

### 3.1 参数定义

```python
@pipeline_command.command(name="generate")
@click.option("--config", "-c",
    type=click.Path(exists=True),
    default="configs/metadata_config.yaml",
    show_default=True,
    help="metadata 配置文件路径")
@click.option("--sql-rag-config",
    type=click.Path(exists=True),
    default="configs/sql_rag.yaml",
    show_default=True,
    help="SQL RAG 配置文件路径")
@click.option("--loader-config",
    type=click.Path(exists=True),
    default="configs/loader_config.yaml",
    show_default=True,
    help="loader 配置文件路径（用于确定 dim_tables.yaml 目标路径）")
@click.option("--domains-config",
    type=click.Path(exists=False),
    default="configs/db_domains.yaml",
    show_default=True,
    help="domain 配置文件路径")
@click.option("--description",
    type=str, default=None,
    help="可选：生成 db_domains.yaml 时的业务背景说明")
@click.option("--regenerate-configs",
    is_flag=True, default=False,
    help="备份并重新生成配置型 YAML 文件（db_domains.yaml, dim_tables.yaml）")
@click.option("--clean",
    is_flag=True, default=False,
    help="清理 output/* 目录后重新生成")
@click.option("--debug",
    is_flag=True, default=False,
    help="启用调试模式")
def pipeline_generate(config, sql_rag_config, loader_config,
                      domains_config, description,
                      regenerate_configs, clean, debug):
    ...
```

### 3.2 执行流程

固定 9 步串行执行，采用**步骤级 fail-fast** 策略（任一步骤整体失败则终止后续步骤；sql-rag 步骤内部允许部分失败，详见 3.4 步骤 8/9 说明）：

```text
步骤 1: ddl
步骤 2: md
步骤 3: generate-domains
步骤 4: json_llm
步骤 5: dim_config --generate
步骤 6: rel_llm
步骤 7: cql
步骤 8: sql-rag generate
步骤 9: sql-rag validate/repair
```

### 3.3 步骤间共享上下文

各步骤通过一个 `_PipelineContext` dataclass 共享状态，避免在主循环和步骤函数之间传递大量零散参数：

```python
@dataclass
class _PipelineContext:
    """pipeline generate 的步骤间共享上下文"""
    project_root: Path
    config_path: Path                  # metadata_config.yaml 绝对路径
    loaded_config: dict                # metadata_config 解析结果
    domains_path: Path                 # db_domains.yaml 绝对路径
    sql_rag_cfg_path: Path             # sql_rag.yaml 绝对路径
    loader_cfg_path: Path              # loader_config.yaml 绝对路径
    description: str | None            # --description 参数
    regenerate_configs: bool           # --regenerate-configs 参数

    # 步骤间传递的中间产物（由步骤执行时填充）
    sql_rag_gen_result: Any = None     # 步骤 8 产出，供步骤 9 使用
    sql_rag_cfg: dict = field(default_factory=dict)  # 步骤 8 加载，供步骤 9 复用
    llm_service: Any = None            # 步骤 8 创建，供步骤 9 修复使用
```

### 3.4 编排主循环伪代码

```python
GENERATE_STEPS = [
    "ddl", "md", "generate-domains", "json_llm",
    "dim_config", "rel_llm", "cql",
    "sql-rag-generate", "sql-rag-validate",
]

def pipeline_generate(...):
    # 0. 初始化
    project_root = get_project_root()
    config_path = _resolve(config, project_root)
    loaded_config = load_config(config_path)

    ctx = _PipelineContext(
        project_root=project_root,
        config_path=config_path,
        loaded_config=loaded_config,
        domains_path=_resolve(domains_config, project_root),
        sql_rag_cfg_path=_resolve(sql_rag_config, project_root),
        loader_cfg_path=_resolve(loader_config, project_root),
        description=description,
        regenerate_configs=regenerate_configs,
    )

    # 0.1 日志提示
    if not clean:
        logger.info("未启用 --clean，将覆盖同名文件，但不会删除历史产物。")
        logger.warning("如果本次生成范围与上次不同，目录中可能残留旧文件；如需全量重建，请使用 --clean。")

    # 0.2 clean: 清空全部 output 子目录
    if clean:
        _clean_all_output_dirs(ctx.loaded_config, ctx.sql_rag_cfg_path, ctx.project_root)

    # 1-9. 逐步执行
    for step_name in GENERATE_STEPS:
        set_current_step(step_name)
        click.echo(f"▶️  开始步骤: {step_name}")

        try:
            _run_generate_step(step_name, ctx)
        except _StepError as e:
            _log_step_failure(e.step_name, str(e), e.errors)
            raise click.Abort()
        except Exception as e:
            _log_step_failure(step_name, str(e))
            logger.error("步骤内部未捕获异常 [%s]", step_name, exc_info=True)
            raise click.Abort()

        click.echo(f"✅ {step_name} 完成")

    click.echo("✨ pipeline generate 全部完成！")
```

### 3.5 各步骤实现细节

#### 步骤 1: ddl

复用 `MetadataGenerator`：

```python
from metaweave.core.metadata.generator import MetadataGenerator

generator = MetadataGenerator(config_path)
result = generator.generate(step="ddl")
if not result.success or result.failed_tables > 0:
    raise _StepError("ddl", result.errors)
```

#### 步骤 2: md

复用 `MetadataGenerator`，需要前置检查 DDL 文件存在：

```python
# 检查 ddl 目录是否有文件
ddl_dir = _resolve_output_dir("ddl", loaded_config)
if not list(ddl_dir.glob("*.sql")):
    raise _StepError("md", ["DDL 目录为空，请先执行 ddl 步骤"])

generator = MetadataGenerator(config_path)
result = generator.generate(step="md")
```

#### 步骤 3: generate-domains

复用 `DomainGenerator`，需要处理配置型文件的跳过/备份逻辑：

```python
from metaweave.core.metadata.domain_generator import DomainGenerator

# 配置型文件保守处理
if ctx.domains_path.exists() and not ctx.regenerate_configs:
    logger.warning(f"{ctx.domains_path} 已存在，跳过生成。")
    logger.warning("如需备份旧文件并重新生成，请使用 --regenerate-configs。")
else:
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
```

#### 步骤 4: json_llm

复用 `metadata_cli.py` 中 `all_llm` 流程的 `json_llm` 逻辑（两阶段串行）：

```python
from metaweave.core.metadata.json_llm_enhancer import JsonLlmEnhancer

# 阶段 1: 生成全量 JSON
generator = MetadataGenerator(config_path)
result_a = generator.generate(step="json")
if not result_a.success or result_a.failed_tables > 0:
    raise _StepError("json_llm", ["阶段 1 (json) 失败"])

# 阶段 2: LLM 增强
json_dir = generator.formatter.json_dir.resolve()
json_files = [
    Path(p) for p in result_a.output_files
    if Path(p).suffix == ".json" and Path(p).resolve().parent == json_dir
]
if not json_files:
    raise _StepError("json_llm", ["阶段 1 未生成任何 JSON 文件"])

cli_config = copy.deepcopy(generator.config)
if "llm" in cli_config and "langchain_config" in cli_config["llm"]:
    cli_config["llm"]["langchain_config"]["use_async"] = False

enhancer = JsonLlmEnhancer(cli_config)
enhancer.enhance_json_files(json_files)
```

#### 步骤 5: dim_config --generate

复用 `DimTableConfigGenerator`，需要处理配置型文件跳过/备份，并从 `loader_config.yaml` 读取目标路径：

```python
from metaweave.core.dim_value.config_generator import DimTableConfigGenerator

# 从 loader_config 获取 dim_tables.yaml 目标路径
loader_cfg = _load_yaml(ctx.loader_cfg_path)
dim_tables_path = _resolve(
    loader_cfg.get("dim_loader", {}).get("config_file", "configs/dim_tables.yaml"),
    ctx.project_root,
)

# 配置型文件保守处理
if dim_tables_path.exists() and not ctx.regenerate_configs:
    logger.warning(f"{dim_tables_path} 已存在，跳过生成。")
    logger.warning("如需备份旧文件并重新生成，请使用 --regenerate-configs。")
else:
    if dim_tables_path.exists() and ctx.regenerate_configs:
        _backup_config_file(dim_tables_path)

    json_dir = _resolve_output_dir("json", ctx.loaded_config)
    gen = DimTableConfigGenerator(json_dir=json_dir, output_path=dim_tables_path)
    gen.generate()
```

#### 步骤 6: rel_llm

复用 `LLMRelationshipDiscovery` + `RelationshipWriter`。需要初始化 `DatabaseConnector` 和 `DomainResolver`：

```python
from metaweave.core.relationships.llm_relationship_discovery import LLMRelationshipDiscovery
from metaweave.core.relationships.writer import RelationshipWriter
from metaweave.core.metadata.connector import DatabaseConnector
from metaweave.core.domains import DomainResolver

connector = DatabaseConnector(ctx.loaded_config.get("database", {}))
try:
    # pipeline generate 中 domain 固定使用 "all"
    domain_resolver = DomainResolver(ctx.domains_path) if ctx.domains_path.exists() else None

    discovery = LLMRelationshipDiscovery(
        config=ctx.loaded_config,
        connector=connector,
        domain_filter="all",       # 统一流程使用所有 domain
        cross_domain=True,         # 包含跨域关系，确保产物完整
        domain_resolver=domain_resolver,
    )

    if not discovery.json_dir.exists():
        raise _StepError("rel_llm", [f"json 目录不存在: {discovery.json_dir}"])

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
```

**跨域关系说明**：pipeline generate 定位为"生成完整产物"，因此默认启用 `cross_domain=True`，同时覆盖域内和跨域关系。如果用户只需要域内关系，应使用单步命令 `metaweave metadata --step rel_llm --domain all`。

#### 步骤 7: cql

复用 `CQLGenerator`，注入 `DomainResolver`：

```python
from metaweave.core.cql_generator.generator import CQLGenerator
from metaweave.core.domains import DomainResolver

cql_resolver = DomainResolver(ctx.domains_path) if ctx.domains_path.exists() else None
generator = CQLGenerator(ctx.config_path, domain_resolver=cql_resolver)
result = generator.generate(step_name="cql")
if not result.success:
    raise _StepError("cql", result.errors)
```

#### 步骤 8: sql-rag generate

复用 `QuestionSQLGenerator`：

```python
from metaweave.services.llm_service import LLMService
from metaweave.core.sql_rag.generator import QuestionSQLGenerator

# 加载 sql_rag.yaml
sql_rag_cfg = _load_yaml(ctx.sql_rag_cfg_path)

generation_config = sql_rag_cfg.get("generation", {})

llm_service = LLMService(ctx.loaded_config.get("llm", {}))
generator = QuestionSQLGenerator(llm_service, generation_config)

md_dir = _resolve_md_dir(ctx.loaded_config)

gen_result = generator.generate(
    domains_config_path=str(ctx.domains_path),
    md_dir=str(md_dir),
)
if not gen_result.success:
    raise _StepError("sql-rag-generate", ["Question-SQL 生成失败（全部 domain 均无有效产出）"])

# 域级失败判定：检查是否有 domain 生成数为 0（但被底层吞掉异常）
failed_domains = [d for d, count in gen_result.domain_stats.items() if count == 0]
if failed_domains:
    logger.warning("以下 domain 生成数为 0（可能存在异常）: %s", failed_domains)
```

**域级失败判定说明**：`QuestionSQLGenerator.generate()` 会吞掉单个 domain 的异常（只要其他 domain 有产出就返回 `success=True`）。pipeline 层在步骤 8 后额外检查 `domain_stats` 中生成数为 0 的 domain，以 warning 形式记录。当前版本不因域级部分失败而终止流程，但日志中会明确提示。

步骤 8 执行完毕后，将中间产物写入上下文供步骤 9 使用：

```python
ctx.sql_rag_gen_result = gen_result
ctx.sql_rag_cfg = sql_rag_cfg
ctx.llm_service = llm_service
```

#### 步骤 9: sql-rag validate/repair

复用 `SQLValidator`：

```python
from metaweave.core.sql_rag.validator import SQLValidator

validation_config = ctx.sql_rag_cfg.get("validation", {})
enable_repair = validation_config.get("enable_sql_repair", False)

repair_llm = ctx.llm_service if enable_repair else None

md_dir_str = str(_resolve_md_dir(ctx.loaded_config))
rel_dir_str = str(_resolve_output_dir("rel", ctx.loaded_config))

validator = SQLValidator(
    connector=connector_for_validate,
    config=validation_config,
    llm_service=repair_llm,
    md_dir=md_dir_str,
    rel_dir=rel_dir_str,
)

stats = validator.validate_file(
    input_file=ctx.sql_rag_gen_result.output_file,   # 来自步骤 8
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
            stats["total"], final_valid, final_invalid,
        )
    else:
        # 未启用修复时，无效 SQL 仍保留在文件中
        # SQLExampleLoader 不校验 SQL 有效性，会原样装载进向量库
        # 因此必须在此处阻断，避免污染向量库
        raise _StepError("sql-rag-validate", [
            f"校验完成但存在 {final_invalid} 条无效 SQL（未启用修复）",
            "请启用 sql_rag.yaml -> validation.enable_sql_repair 或手工修正后重新执行",
        ])
```

**SQL 质量判定说明**：`SQLValidator.validate_file()` 不会因存在无效 SQL 而抛出异常，它只返回统计结果并写报告。pipeline 层在步骤 9 后主动检查最终无效数：

1. **启用 `enable_sql_repair` 时**：修复失败的条目已被自动从文件中删除，剩余均为有效 SQL，流程继续
2. **未启用修复且存在无效 SQL 时**：抛出 `_StepError` 终止流程。原因是 `SQLExampleLoader` 不校验 SQL 有效性，会将无效 SQL 原样装载进向量库，污染下游检索质量

注意：sql-rag validate 需要数据库连接（用于 EXPLAIN）。该连接应在步骤 8 之前创建，步骤 9 结束后关闭。连接生命周期管理方案见 3.7 节。

### 3.6 配置型文件备份函数

```python
from datetime import datetime

def _backup_config_file(file_path: Path) -> Path:
    """备份配置文件，返回备份路径。

    命名规则：<原文件名>.bak_yyyyMMdd_HHmmss
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = file_path.parent / f"{file_path.name}.bak_{ts}"
    shutil.copy2(file_path, backup_path)
    logger.info(f"已备份: {file_path} -> {backup_path}")
    return backup_path
```

### 3.7 数据库连接生命周期

pipeline generate 涉及多个需要数据库连接的步骤。连接管理策略如下：

| 步骤 | 需要 DB 连接 | 说明 |
|------|-------------|------|
| ddl | 是 | `MetadataGenerator` 内部管理 |
| md | 是 | `MetadataGenerator` 内部管理 |
| generate-domains | 否 | 基于 MD 文件 + LLM |
| json_llm | 是 | `MetadataGenerator` 内部管理 |
| dim_config | 否 | 仅读取 JSON 文件 |
| rel_llm | 是 | 需要外部传入 `DatabaseConnector` |
| cql | 否 | 仅读取 JSON + REL 文件 |
| sql-rag generate | 否 | 基于 MD 文件 + LLM |
| sql-rag validate | 是 | 需要 `DatabaseConnector` 做 EXPLAIN |

策略：

1. `ddl`、`md`、`json_llm` 由 `MetadataGenerator` 内部创建和关闭连接，pipeline 无需干预
2. `rel_llm` 需要外部传入 `DatabaseConnector`，在该步骤前创建、步骤后关闭
3. `sql-rag validate` 需要 `DatabaseConnector`，在步骤 8 前创建、步骤 9 后关闭

```python
# rel_llm 步骤
connector_rel = DatabaseConnector(loaded_config.get("database", {}))
try:
    _run_rel_llm(connector_rel, ...)
finally:
    connector_rel.close()

# sql-rag 步骤（8+9 共享连接）
connector_sql = DatabaseConnector(loaded_config.get("database", {}))
try:
    gen_result = _run_sql_rag_generate(...)       # 步骤 8（不使用连接）
    _run_sql_rag_validate(connector_sql, ...)      # 步骤 9
finally:
    connector_sql.close()
```

### 3.8 --clean 对 output 目录的清理

`--clean` 时，在执行第一个步骤前，一次性清空所有 output 子目录：

```python
def _clean_all_output_dirs(loaded_config: dict, sql_rag_config_path: Path, project_root: Path):
    """清空全部 output 子目录。

    Args:
        loaded_config: 已加载的 metadata_config 字典
        sql_rag_config_path: sql_rag.yaml 的绝对路径（用于读取 sql 输出目录）
        project_root: 项目根目录
    """
    output_cfg = loaded_config.get("output", {})
    output_dir = Path(output_cfg.get("output_dir", "output"))
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir

    # 1. 清理 metadata 相关 output 子目录
    sub_dirs = ["ddl", "md", "json", "rel", "cql"]
    dir_keys = {
        "ddl": "ddl_directory",
        "md": "markdown_directory",
        "json": "json_directory",
        "rel": "rel_directory",
        "cql": "cql_directory",
    }
    for sub in sub_dirs:
        key = dir_keys[sub]
        d = output_cfg.get(key)
        if d:
            d = Path(d)
            if not d.is_absolute():
                d = project_root / d
        else:
            d = output_dir / sub
        if d.exists():
            clear_dir_contents(d)
            logger.debug(f"已清空: {d}")

    # 2. 清理 sql 输出目录（从 sql_rag.yaml 读取）
    sql_rag_cfg = _load_yaml(sql_rag_config_path)
    sql_output_dir = _resolve(
        sql_rag_cfg.get("generation", {}).get("output_dir", "output/sql"),
        project_root,
    )
    if sql_output_dir.exists():
        clear_dir_contents(sql_output_dir)
        logger.debug(f"已清空: {sql_output_dir}")
```

注意：`--clean` 仅作用于 `output/*`，不影响 `configs/*` 下的配置型文件。

## 4. pipeline load 详细设计

### 4.1 参数定义

```python
@pipeline_command.command(name="load")
@click.option("--config", "-c",
    type=click.Path(exists=True),
    default="configs/metadata_config.yaml",
    show_default=True,
    help="metadata 配置文件路径")
@click.option("--loader-config",
    type=click.Path(exists=True),
    default="configs/loader_config.yaml",
    show_default=True,
    help="loader 配置文件路径")
@click.option("--with-dim-values",
    is_flag=True, default=False,
    help="是否加载 dim_value（需要已确认 dim_tables.yaml）")
@click.option("--clean",
    is_flag=True, default=False,
    help="加载前清理目标库/集合")
@click.option("--debug",
    is_flag=True, default=False,
    help="启用调试模式")
def pipeline_load(config, loader_config, with_dim_values, clean, debug):
    ...
```

### 4.2 执行流程

固定 3+1 步串行执行：

```text
步骤 1: load cql          -> Neo4j
步骤 2: load table_schema -> Milvus (读取 loader_config.yaml -> table_schema_loader.collection_name)
步骤 3: load sql           -> Milvus (读取 loader_config.yaml -> sql_loader.collection_name)
步骤 4: load dim_value     -> Milvus (读取 loader_config.yaml -> dim_loader.collection_name)  [仅 --with-dim-values]
```

### 4.3 编排主循环伪代码

```python
LOAD_STEPS = ["cql", "table_schema", "sql"]

def pipeline_load(...):
    project_root = get_project_root()
    loader_cfg_path = _resolve(loader_config, project_root)
    loader_cfg = _load_yaml(loader_cfg_path)

    # 追加 metadata_config 引用，供向量加载器读取公共配置
    # （loader 构造时需要 metadata_config_file 指向 metadata_config.yaml）
    loader_cfg["metadata_config_file"] = str(_resolve(config, project_root))

    steps = list(LOAD_STEPS)
    if with_dim_values:
        # 前置校验：dim_tables.yaml 必须存在
        dim_cfg_file = loader_cfg.get("dim_loader", {}).get("config_file", "configs/dim_tables.yaml")
        dim_cfg_path = _resolve(dim_cfg_file, project_root)
        if not dim_cfg_path.exists():
            raise click.UsageError(
                f"dim_tables.yaml 不存在: {dim_cfg_path}\n"
                f"请先执行 pipeline generate 或手工创建该文件"
            )
        steps.append("dim_value")

    if clean:
        click.echo("⚠️  --clean 将在每个 loader 执行前清理对应目标库/集合")

    for step_name in steps:
        click.echo(f"▶️  开始加载: {step_name}")

        loader = LoaderFactory.create(step_name, loader_cfg)
        if not loader.validate():
            raise click.ClickException(f"{step_name} loader 验证失败")

        result = loader.load(clean=clean)
        if not result.get("success"):
            click.echo(f"❌ {step_name} 加载失败: {result.get('message')}", err=True)
            raise click.Abort()

        click.echo(f"✅ {step_name} 加载完成")

    click.echo("✨ pipeline load 全部完成！")
```

### 4.4 各步骤的清理目标

| 步骤 | `--clean` 清理目标 | 说明 |
|------|-------------------|------|
| cql | **清空目标 Neo4j 数据库中的全部节点与关系**（`MATCH (n) DETACH DELETE n`） | 由 `CQLLoader.load(clean=True)` 处理 |
| table_schema | `loader_config.yaml -> table_schema_loader.collection_name` 对应的 Milvus collection | 由 `TableSchemaLoader.load(clean=True)` 处理 |
| sql | `loader_config.yaml -> sql_loader.collection_name` 对应的 Milvus collection | 由 `SQLExampleLoader.load(clean=True)` 处理 |
| dim_value | `loader_config.yaml -> dim_loader.collection_name` 对应的 Milvus collection | 由 `DimValueLoader.load(clean=True)` 处理 |

清理逻辑已在各 loader 内部实现，pipeline 层只需将 `clean` 参数透传。

### 4.5 loader 配置传递

当前 `LoaderFactory.create(load_type, config)` 接受完整的 loader_config 字典。各 loader 在 `__init__` 中从字典中取自己关心的子节点。因此 pipeline 只需将 `loader_config.yaml` 加载为字典后传入即可。

部分 loader（如 `TableSchemaLoader`、`DimValueLoader`、`SQLExampleLoader`）还需要从 `metadata_config.yaml` 读取 `embedding`、`vector_database` 等公共配置。当前 `loader_config.yaml` 中有 `metadata_config_file` 字段指向 `metadata_config.yaml`，loader 内部会自行加载。

**pipeline 层始终用 CLI `--config` 参数覆盖 `loader_cfg["metadata_config_file"]`**（见 4.3 节伪代码），确保 CLI 参数优先级最高，避免 `loader_config.yaml` 和 `--config` 指向不同 metadata 配置时产生不一致。

## 5. 辅助函数设计

以下辅助函数应放在 `pipeline_cli.py` 内部（模块级私有函数）：

### 5.1 路径解析

```python
def _resolve(path_str: str, project_root: Path) -> Path:
    """相对路径基于项目根目录解析为绝对路径"""
    p = Path(path_str)
    if not p.is_absolute():
        p = project_root / p
    return p
```

### 5.2 output 子目录解析

```python
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
```

### 5.3 MD 目录解析

```python
def _resolve_md_dir(loaded_config: dict) -> Path:
    """解析 markdown 输出目录路径"""
    return _resolve_output_dir("md", loaded_config)
```

### 5.4 YAML 加载

```python
def _load_yaml(path: Path) -> dict:
    """加载 YAML 文件，不存在返回空字典"""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
```

## 6. 日志与输出设计

### 6.1 步骤切换日志

使用 `set_current_step()` 在步骤切换时更新日志上下文，与现有 `all_llm` 模式保持一致。

### 6.2 输出格式

```text
🚀 开始 pipeline generate
🧭 调度顺序: ddl -> md -> generate-domains -> json_llm -> dim_config -> rel_llm -> cql -> sql-rag-generate -> sql-rag-validate

============================================================
▶️  开始步骤: ddl
============================================================
...（步骤内部输出）
✅ ddl 完成

============================================================
▶️  开始步骤: md
============================================================
...

[WARN] /path/to/configs/db_domains.yaml 已存在，跳过生成。
[WARN] 如需备份旧文件并重新生成，请使用 --regenerate-configs。

...

✨ pipeline generate 全部完成！
```

### 6.3 未启用 --clean 时的提示

在执行第一个步骤前输出：

```text
[INFO] 未启用 --clean，将覆盖同名文件，但不会删除历史产物。
[WARN] 如果本次生成范围与上次不同，目录中可能残留旧文件；如需全量重建，请使用 --clean。
```

## 7. 错误处理设计

### 7.1 _StepError

定义一个模块内部异常类（下划线前缀表示 `pipeline_cli.py` 私有），用于步骤失败时携带步骤名和错误详情：

```python
class _StepError(Exception):
    """pipeline 步骤执行失败"""
    def __init__(self, step_name: str, errors: list[str] | None = None):
        self.step_name = step_name
        self.errors = errors or []
        super().__init__(f"步骤失败 [{step_name}]")
```

### 7.2 fail-fast 处理

主循环统一只捕获两类异常：`_StepError`（步骤主动抛出，携带结构化错误列表）和兜底 `Exception`（未预期异常）。两者均通过 `_log_step_failure()` 输出错误摘要，确保所有步骤的错误输出格式一致：

```python
try:
    _run_step(step_name, ...)
except _StepError as e:
    _log_step_failure(e.step_name, str(e), e.errors)
    raise click.Abort()
except Exception as e:
    _log_step_failure(step_name, str(e))
    logger.error("步骤内部未捕获异常 [%s]", step_name, exc_info=True)
    raise click.Abort()
```

两类异常分支的用户可见输出完全一致（均通过 `_log_step_failure` 格式化），区别仅在于兜底分支额外记录完整堆栈到日志文件（`exc_info=True`）。

### 7.3 错误摘要格式

与现有 `metadata_cli.py` 保持一致，最多显示前 10 条错误：

```python
def _log_step_failure(step_name: str, message: str, errors: list[str] | None = None):
    logger.error("步骤失败 [%s]: %s", step_name, message)
    click.echo(f"❌ 步骤失败 [{step_name}]: {message}", err=True)
    if errors:
        for e in errors[:10]:
            click.echo(f"  - {e}", err=True)
        if len(errors) > 10:
            click.echo(f"  ... 还有 {len(errors) - 10} 个错误", err=True)
```

## 8. 与现有命令的关系

### 8.1 不替代现有命令

`pipeline generate` 是一个**编排快捷方式**，近似等价于按顺序执行以下能力：

```text
1. metaweave metadata --step ddl
2. metaweave metadata --step md
3. metaweave metadata --generate-domains [--description ...]
4. metaweave metadata --step json_llm
5. metaweave dim_config --generate
6. metaweave metadata --step rel_llm --domain all --cross-domain
7. metaweave metadata --step cql
8. metaweave sql-rag generate
9. metaweave sql-rag validate（输入文件由步骤 8 的产出自动传递）
```

`pipeline load` 近似等价于：

```text
1. metaweave load --type cql
2. metaweave load --type table_schema
3. metaweave load --type sql
4. metaweave load --type dim_value   （仅 --with-dim-values 时）
```

注意：上述为能力层面的近似对应，pipeline 内部通过代码直接调用底层模块，并非逐条拼接 CLI 命令。部分参数（如步骤间的产物路径传递、`--config` 对 `loader_config.yaml` 中 `metadata_config_file` 的覆盖）由 pipeline 自动处理，无法通过单步命令简单复现。

### 8.2 不暴露单步参数

`pipeline` 命令**不支持**以下在单步命令中可用的参数：

- `--schemas` / `--tables`（pipeline 固定处理全部表）
- `--incremental`（pipeline 固定全量生成）
- `--max-workers`（使用默认并发数 4）
- `--domain` / `--cross-domain`（pipeline 固定使用全部 domain + 跨域关系）
- `--step`（pipeline 固定走完整流程）

如果用户需要精细控制，应使用原有的单步命令。

## 9. 测试策略

### 9.1 单元测试

在 `tests/unit/` 下新增：

| 文件 | 覆盖内容 |
|------|---------|
| `test_pipeline_generate.py` | 测试 `_backup_config_file`、`_clean_all_output_dirs`、`_resolve_output_dir` 等辅助函数 |
| `test_pipeline_load.py` | 测试 `pipeline_load` 的参数校验逻辑（如 `--with-dim-values` 时文件不存在应报错） |

### 9.2 集成测试

pipeline 的集成测试依赖完整的数据库和 LLM 环境，不适合在 CI 中自动运行。建议：

1. 使用手动测试验证完整流程
2. 在 `tests/integration/` 下编写标记为 `@pytest.mark.integration` 的测试，在有环境时手动触发

### 9.3 最小测试清单

以下为实施后必须通过的测试用例，分为单元测试（UT）和手动集成测试（IT）。

#### 9.3.1 单元测试（不依赖外部服务）

| ID | 测试用例 | 预期结果 |
|----|---------|---------|
| UT-01 | `_backup_config_file` 对已存在文件 | 生成 `.bak_yyyyMMdd_HHmmss` 备份，原文件保留 |
| UT-02 | `_backup_config_file` 备份文件名时间戳格式 | 符合 `%Y%m%d_%H%M%S` |
| UT-03 | `_resolve_output_dir("json", config)` 有 `json_directory` 配置 | 返回配置值的绝对路径 |
| UT-04 | `_resolve_output_dir("json", config)` 无 `json_directory` 配置 | 返回 `output_dir/json` |
| UT-05 | `_clean_all_output_dirs` 正常清空 6 个子目录 | 所有子目录内容被清空，目录本身保留 |
| UT-06 | `_clean_all_output_dirs` 的 sql 目录从 `sql_rag.yaml` 读取 | 正确读取 `generation.output_dir` 并清空 |
| UT-07 | `pipeline load --with-dim-values` 且 `dim_tables.yaml` 不存在 | `click.UsageError` 并终止 |
| UT-08 | `pipeline load` 不传 `--with-dim-values` | 步骤列表不含 `dim_value` |
| UT-09 | `_StepError` 携带错误列表 | `_log_step_failure` 输出前 10 条并显示剩余数量 |

#### 9.3.2 集成测试（需要 DB + LLM 环境）

| ID | 测试场景 | 验证点 |
|----|---------|--------|
| IT-01 | `pipeline generate` 正常全流程 | 9 步全部成功；`output/{ddl,md,json,rel,cql,sql}` 均有文件；`configs/db_domains.yaml` 和 `configs/dim_tables.yaml` 已生成 |
| IT-02 | `pipeline generate --clean` | 执行前在 `output/json` 放入无关文件，执行后该文件不存在 |
| IT-03 | `pipeline generate --regenerate-configs` | `db_domains.yaml.bak_*` 和 `dim_tables.yaml.bak_*` 存在；新配置文件内容为本次生成结果 |
| IT-04 | `pipeline generate`（configs 已存在） | 日志输出"已存在，跳过生成"；已有配置文件内容未变 |
| IT-05 | `pipeline generate` 中间步骤失败 | 模拟 `rel_llm` 失败（如断开 DB）；`cql` 和 `sql-rag` 步骤不执行；退出码非 0 |
| IT-06 | `pipeline generate --domains-config custom/path.yaml` | domain 配置文件生成在自定义路径；日志中显示实际路径而非默认路径 |
| IT-07 | `pipeline load` 默认 | cql + table_schema + sql 加载成功；dim_value 未触发 |
| IT-08 | `pipeline load --with-dim-values` | 4 个 loader 全部执行成功 |
| IT-09 | `pipeline load --clean` | 各 loader 执行前清理对应目标库/集合 |
| IT-10 | `pipeline load --with-dim-values`（`dim_tables.yaml` 不存在） | 报错并终止，不执行任何 loader |
| IT-11 | `pipeline load --loader-config custom/loader.yaml` | 使用自定义 loader 配置文件路径 |
| IT-12 | `pipeline generate`，`enable_sql_repair=true` 且部分 SQL 修复失败 | 不抛 `_StepError`；修复失败的条目已从输出文件删除；日志输出 warning 含"修复失败 N 条（已从文件删除）" |
| IT-13 | `pipeline generate`，`enable_sql_repair=false` 且存在无效 SQL | 步骤 9 抛 `_StepError` 终止流程；后续 load 不执行 |
