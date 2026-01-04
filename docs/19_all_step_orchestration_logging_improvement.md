# 19_全流程编排日志改进方案 (all/all_llm)

## 1. 背景与目标
当前执行 `metaweave metadata --step all_llm` 或 `--step all` 时，日志与输出系统存在全局视角缺失、失败路径日志断裂以及输出位置不统一等问题。本项目标是实现统一的 `all.log`，并重构编排逻辑以确保日志上下文切换的安全性和准确性。

## 2. 影响文件
- `configs/logging.yaml`: 修改日志文件名和过滤器配置。
- `metaweave/cli/metadata_cli.py`: 重构异常处理、日志记录及控制台输出逻辑。
- `docs/17_step_based_logging_refactor.md`: 更新文档以反映日志文件名的变更。

## 3. 修改详细规划

### 3.1 日志配置修改 (configs/logging.yaml)
需同时修改过滤器范围和输出文件名，具体配置如下：

```yaml
filters:
  # ... 其他 filter ...
  all_filter:
    (): metaweave.utils.logger.StepFilter
    allowed_steps: ['all', 'all_llm']  # 关键：必须包含 all_llm

handlers:
  # ... 其他 handler ...
  all_file:
    class: logging.handlers.RotatingFileHandler
    level: DEBUG
    formatter: detailed
    filename: logs/all.log             # 关键：改为 all.log
    maxBytes: 10485760
    backupCount: 5
    encoding: utf8
    filters: [all_filter]
```

### 3.2 CLI 逻辑重构 (metaweave/cli/metadata_cli.py)

#### 3.2.1 关键开发约束与原则

1.  **并发安全边界**：
    切回 `parent_step`（写 all.log）**必须且只能**发生在子步骤（包括其所有并发线程）完全结束之后。严禁在子步骤运行过程中切换上下文。

2.  **日志分层原则**：
    - `child.log`：记录完整执行细节和错误堆栈（`exc_info=True`）。
    - `all.log`：仅记录编排层摘要，**不输出**冗长的错误堆栈。
    - **特例**：全局未捕获异常（Global Uncaught Exception）需记录完整堆栈以供排错。

3.  **控制台输出分层**：
    - **编排层进度提示**：在 parent context 中输出。
    - **子步骤内部详细输出**：在 child context 中输出。

#### 3.2.2 特殊步骤说明

1.  **json_llm 的两阶段日志行为**：
    `json_llm` 内部调用 `generator.generate(step="json")` 不会改变全局 `current_step`。日志统一记录在 `logs/json.log`。

2.  **rel_llm 的资源管理与日志**：
    - 需创建 `DatabaseConnector`，必须在 `finally` 块中关闭。

#### 3.2.3 🎯 核心实现参考代码

```python
# === 前置条件：以下变量已在循环外定义 ===
# ... parent_step, steps, loaded_config, schemas_list, tables_list, incremental, max_workers, clean ...
# ... domain, cross_domain, db_domains_config (仅 rel_llm 使用) ...

parent_step = step_lower
set_current_step(parent_step)
logger.info("🚀 开始全流程执行: %s", parent_step)
logger.info("🧭 调度顺序: %s", " -> ".join(steps))

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
                _clean_step_output_dir(child_step, loaded_config)

            # 3. 执行子步骤
            if child_step in {"ddl", "json", "md"}:
                generator = MetadataGenerator(config_path)
                result = generator.generate(
                    schemas=schemas_list, tables=tables_list,
                    incremental=incremental, max_workers=max_workers, step=child_step
                )
                if not result.success or result.failed_tables > 0:
                    step_error_msg = f"处理失败: 成功 {result.processed_tables}，失败 {result.failed_tables}"
                    step_errors = result.errors
                else:
                    step_success = True

            elif child_step == "json_llm":
                from metaweave.core.metadata.json_llm_enhancer import JsonLlmEnhancer
                generator = MetadataGenerator(config_path)
                # 阶段 A: JSON 生成
                click.echo("📊 阶段 1/2: 生成全量 JSON（--step json）...")
                result_a = generator.generate(
                    schemas=schemas_list, tables=tables_list,
                    incremental=incremental, max_workers=max_workers, step="json"
                )
                if not result_a.success or result_a.failed_tables > 0:
                    step_error_msg = "阶段A失败"
                    step_errors = result_a.errors
                else:
                    # 阶段 B: LLM 增强
                    json_dir = (generator.formatter.output_dir / "json").resolve()
                    # 关键修改：严格限制在 json_dir 目录下
                    json_files = [
                        Path(p) for p in result_a.output_files 
                        if Path(p).suffix == ".json" and Path(p).resolve().parent == json_dir
                    ]
                    if not json_files:
                        step_error_msg = "未生成任何JSON文件"
                    else:
                        click.echo("🤖 阶段 2/2: LLM 增强处理...")
                        cli_config = copy.deepcopy(generator.config)
                        enhancer = JsonLlmEnhancer(cli_config)
                        enhancer.enhance_json_files(json_files)
                        step_success = True

            elif child_step == "rel_llm":
                from metaweave.core.relationships.llm_relationship_discovery import LLMRelationshipDiscovery
                from metaweave.core.metadata.connector import DatabaseConnector
                from metaweave.core.relationships.writer import RelationshipWriter
                
                connector = DatabaseConnector(loaded_config.get("database", {}))
                try:
                    discovery = LLMRelationshipDiscovery(
                        config=loaded_config, connector=connector,
                        domain_filter=domain, cross_domain=cross_domain,
                        db_domains_config=db_domains_config
                    )
                    relations, rejected_count, extra_statistics = discovery.discover()
                    writer = RelationshipWriter(loaded_config)
                    output_files = writer.write_results(
                        relations=relations, suppressed=[], config=loaded_config,
                        tables=discovery.tables, generated_by="rel_llm",
                        extra_statistics=extra_statistics
                    )
                    for f in output_files:
                        logger.info("rel_llm 输出文件: %s", f)
                    step_success = True
                finally:
                    connector.close()

            elif child_step == "rel":
                # ... pipeline.discover() ...
                step_success = True

            elif child_step == "cql":
                # ... CQLGenerator.generate() ...
                step_success = True

        except Exception as e:
            logger.error("子步骤内部异常: %s", e, exc_info=True)
            step_success = False
            step_error_msg = str(e)

        # --- 阶段 3: 执行后 (Parent Context) ---
        set_current_step(parent_step)

        if not step_success:
            logger.error("❌ 子步骤失败: %s. 原因: %s", child_step, step_error_msg)
            if step_errors:
                for err in step_errors[:10]:
                    logger.error("  - %s", err)
            logger.error("⛔ 全流程终止")
            click.echo(f"❌ {child_step} 失败: {step_error_msg}", err=True)
            raise click.Abort()
        else:
            logger.info("✅ 子步骤完成: %s", child_step)
            click.echo(f"✅ {child_step} 完成")

    logger.info("✨ 全流程执行成功完成")
    click.echo("")
    click.echo(f"✨ {parent_step} 处理完成！")

except click.Abort:
    set_current_step(parent_step)
    logger.error("🛑 流程被中止")
    raise
except Exception as e:
    set_current_step(parent_step)
    logger.error("❌ 全局未捕获异常: %s", e, exc_info=True)
    click.echo(f"❌ 未预期错误: {e}", err=True)
    raise click.Abort()
```

### 3.3 文档同步
- 修改 `docs/17_step_based_logging_refactor.md`，将 `metaweave_all.log` 统一替换为 `all.log`。

## 4. 验证计划

### 4.1 正常流程验证
1. 执行 `metaweave metadata --step all`
2. 验证：
   - `logs/all.log` 包含起止摘要。
   - `logs/all.log` **不包含**表级别执行细节（如 SQL 查询）。
   - `logs/ddl.log` 等子日志包含详细执行逻辑。

### 4.2 失败流程验证
- 构造 DDL 缺失，验证 `all.log` 包含“❌ 子步骤失败: md. 原因: DDL 目录为空...”。

### 4.3 并发安全验证
- 执行 `metaweave metadata --step all --max-workers 8`，验证 `all.log` 中无交叉污染。

### 4.4 --clean 参数验证
1. 执行 `metaweave metadata --step all --clean`
2. 验证：
   - 清理日志记录在各子日志中。
   - `logs/all.log` **不包含**清理动作的详细记录。

## 5. 评估
- **改动量**：小。通过重构控制流，实现了高可用的编排日志。