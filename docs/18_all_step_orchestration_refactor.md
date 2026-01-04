# 18_ 重构 `--step all`：从“单步多格式”改为“多步骤调度”

## 背景与目标

当前 `metaweave metadata --step all` 属于 `MetadataGenerator` 内部的一种模式：对每张表查库一次，然后按 `output.formats` 同时输出 `ddl/md/json`。它不是“调度多个 step”，也不包含 `rel/cql`。

本变更目标：

1. **删除旧 `--step all` 功能**（`MetadataGenerator` 的 all 模式）。
2. **新增 CLI 级别的 `--step all` / `--step all_llm`**，用于按固定顺序串行调度多个步骤：
   - `all`: `ddl -> md -> json -> rel -> cql`
   - `all_llm`: `ddl -> md -> json_llm -> rel_llm -> cql`
3. **为 `all/all_llm` 支持 `--clean`**：每个子步骤开始写入前清空其对应输出目录（只清当前子步骤目录）。

不考虑兼容性：允许破坏旧语义、删除旧分支、调整 help 文案。

## 新语义定义

### 1) `--step all`

- 执行顺序（固定，不受 YAML 控制）：
  1. `ddl`
  2. `md`
  3. `json`
  4. `rel`
  5. `cql`
- 每个子步骤的内部逻辑保持不变（并发、采样、写文件、LLM 等均沿用现有实现）。
- 默认策略：任一步失败则立即退出（fail-fast）。

### 2) `--step all_llm`

- 执行顺序（固定）：
  1. `ddl`
  2. `md`
  3. `json_llm`
  4. `rel_llm`
  5. `cql`
- 说明：
  - `cql` 与 `cql_llm` 行为等价，统一调用现有生成器即可。

### 3) `--clean`（对 all/all_llm 生效）

为避免“历史产物残留导致 rel/cql 误读旧文件”，`all/all_llm` 支持 `--clean`：

- 清理时机：**每个子步骤写入前**，清空**该子步骤的输出目录**
- 清理范围：**仅清理当前子步骤的输出目录**，不影响其他步骤已经生成的文件（依赖输入仍在）

清理映射表：

| 步骤 | 清理目录 | 说明 |
|------|---------|------|
| `ddl` | `output_dir/ddl` | 清空旧的 DDL 文件 |
| `md` | `output_dir/md` | 清空旧的 Markdown 文件（不影响 ddl 目录） |
| `json`/`json_llm` | `output_dir/json` | 清空旧的 JSON 文件（不影响 ddl/md） |
| `rel`/`rel_llm` | `output.rel_directory` | 清空旧的关系文件（不影响 json） |
| `cql` | `output.cql_directory` | 清空旧的 CQL 文件（不影响 json/rel） |

示例：`--step all --clean` 的清理顺序

1. 清空 `ddl/` → 生成 ddl
2. 清空 `md/` → 从 `ddl/` 读取并生成 md（`ddl/` 文件仍在）
3. 清空 `json/` → 生成 json
4. 清空 `rel/` → 从 `json/` 读取并生成 rel（`json/` 文件仍在）
5. 清空 `cql/` → 从 `json/` + `rel/` 读取并生成 cql

> 注：当前项目已存在 `clear_dir_contents()` 与单步 `--clean` 机制；本变更只需把 `--clean` 放开给 all/all_llm，并在 orchestrator 中按阶段调用。

## 设计方案（实现建议）

### A) 删除旧 `MetadataGenerator` 的 `all` 模式

文件：`metaweave/core/metadata/generator.py`

- 删除/调整：
  - `SUPPORTED_STEPS`：移除 `"all"`
  - `_normalize_step()`：不再接受 `"all"`
  - `_resolve_formats_for_step()`：移除 `"all": self.formatter.formats`
  - `generate()` 内部 `if self.active_step == "all": _generate_summary(...)`：移除
  - `SUPPORTED_STEPS` 中的 `"cql"` 如仍保留但未实现，可维持现状或进一步收敛（不属于本次核心）。

效果：`MetadataGenerator.generate(step="all")` 不再存在；全流程调度统一由 CLI 实现。

### B) 在 CLI 实现 orchestrator：`all` 与 `all_llm`

文件：`metaweave/cli/metadata_cli.py`

1. `--step` 增加 `all_llm`（并保留 `all`）
2. 增加内部调度函数（建议拆小）：
   - `_run_metadata_step(step_name)`：调用 `MetadataGenerator.generate(step=...)`，适用于 `ddl/json/md`
   - `_run_json_llm()`：复用现有两阶段逻辑（阶段1 `json` + 阶段2 enhancer）
   - `_run_rel()` / `_run_rel_llm()`：复用现有分支逻辑
   - `_run_cql(step_name)`：复用现有 `CQLGenerator.generate(step_name=...)`
3. `all/all_llm` 分支只做串行编排：
   - `all` 的 steps：`["ddl", "md", "json", "rel", "cql"]`
   - `all_llm` 的 steps：`["ddl", "md", "json_llm", "rel_llm", "cql"]`

### C) 日志 step 的切换（关键）

当前 step-based logging 依赖 `set_current_step(...)` 决定写入哪个 `logs/{step}.log`。

因此 `all/all_llm` 必须：

- 在每个子步骤开始前调用 `set_current_step(child_step)`（例如 `ddl/md/json/...`）
- 保证该子步骤内所有日志都落到对应文件中（不使用旧 `all` 的单一日志文件策略）

新方案的日志行为（含并发）：

- orchestrator 层：串行调度多个子步骤，step 切换点明确（仅发生在子步骤边界）。
- 子步骤层：子步骤内部可能并发处理多张表，但 **子步骤执行期间 step 保持不变**。
  - 例如进入 `ddl` 子步骤后先 `set_current_step("ddl")`，随后 `ddl` 内部的并发线程共享同一个全局 step 值，因此所有日志都会稳定写入 `logs/ddl.log`。
  - `md/json/...` 同理。

补充说明（为什么旧 all 不建议拆分日志）：

- 旧 `MetadataGenerator --step all` 并不是“多步骤调度”，而是单一模式，且内部会并发处理表。
- 项目当前的 step 是全局变量（非线程局部），如果在并发执行中频繁切换 step，会导致日志跨文件串写/写错文件。
- 新的 CLI orchestrator 方案是“按步骤串行调度”，每个子步骤内部保持 step 不变，因此可以稳定地按步骤拆分日志文件。

### D) `--clean` 在 all/all_llm 的行为

文件：`metaweave/cli/metadata_cli.py`

- 取消“`--clean` 不支持 all”的限制
- orchestrator 按子步骤调用 `_clean_step_output_dir(child_step, loaded_config)`
  - 配置来源：
    - `ddl/json/md/json_llm`：可用 `MetadataGenerator(config_path).config`（已解析 env）
    - `rel/rel_llm`：用 `load_config(config_path)`
    - `cql`：可用 `CQLGenerator(config_path).config`
- 推荐实现：复用现有 `_clean_step_output_dir()`，只需要在 orchestrator 里按阶段调用即可

## 参数透传与一致性约束

- `--schemas/--tables/--max-workers/--incremental`：
  - 仅对 `ddl/md/json/json_llm(阶段A)` 生效（现状如此）
  - `rel/cql` 默认会读取目录中“全部”产物，因此 **强烈建议配合 `--clean` 使用**，确保目录内只有本次产物
- `md` 依赖 `ddl`：all/all_llm 的顺序已保证；保留现有 md 的 DDL 目录检查即可

## 失败处理策略（建议）

- 默认 fail-fast：任一子步骤“失败”即退出，不做 table 级恢复。

失败的定义（建议统一为“步骤级失败”）：

- **异常失败**：子步骤抛出未捕获异常 / CLI 分支 `raise click.Abort()` / `ClickException`（即当前命令返回非 0）。
- **结果失败**：子步骤返回 result 对象且满足任一条件：
  - `success == False`
  - 或 `failed_tables > 0`（仅适用于 `ddl/md/json/json_llm 阶段A` 这类按表统计的步骤）

失败后的行为（建议）：

- 立即退出，并在**控制台**与**日志**中同时输出：
  - 出错的子步骤名称（例如 `rel_llm`）
  - 错误原因（异常信息/错误列表摘要）
- 不做额外清理：已生成的文件保持现状（便于排查与支持从中断点继续）。

恢复方式（建议）：

- 从失败步骤继续：使用 `--step {failed_step}` 重新执行（必要时配合 `--clean` 清该步骤输出目录）。
- 从头重跑：使用 `--step all --clean` 或 `--step all_llm --clean`。

可选增强（非本次必须）：增加 `--continue-on-error`（未来再考虑）。

## 最小验证建议

使用 `.venv-wsl`：

1. 导入检查：
   - `python -c "from metaweave.cli.metadata_cli import metadata_command"`
2. 单元测试（建议新增 mock 测试，验证调度顺序与 set_current_step 调用）：
   - `pytest -q tests/unit/test_step_all_orchestrator.py`
3. 手工 smoke（不连网/不跑 LLM 可仅测分支可达性）：
   - `metaweave metadata --config configs/metadata_config.yaml --step all --clean`
