# Step 日志拆分改造规划（不考虑兼容性）

## 目标
- `metaweave metadata --step <x>` 每个 step 写入独立日志文件，文件名与 step 对齐。
- `json/json_llm` 共用一个日志文件；`rel/rel_llm` 共用一个日志文件；`cql/cql_llm` 共用一个日志文件。
- `metaweave load ...`（loader）日志配置保持不变。
- `--step all` 若按阶段拆分成本高，则统一写入 `logs/all.log`。

## 现状问题（简述）
- 当前日志路由以 “logger 名称（模块）→ 文件” 为主，导致 “按 step 执行” 时日志混杂（尤其 metadata 相关）。
- 同一个模块 logger（如 `metaweave.generator`/`metaweave.formatter`）会在不同 step 运行，因此无法仅靠静态 `logging.yaml` 达到按 step 分文件。

## 目标日志文件映射
| CLI step | 日志文件 |
|---|---|
| `ddl` | `logs/ddl.log` |
| `json` / `json_llm` | `logs/json.log` |
| `md` | `logs/md.log` |
| `rel` / `rel_llm` | `logs/rel.log` |
| `cql` / `cql_llm` | `logs/cql.log` |
| `all` | `logs/all.log`（先不做阶段拆分） |
| `load ...` | 保持 `logs/loader.log`（不改） |

## 实现方案（按 step 路由）
### 1) 引入 “当前 step” 运行时上下文
- 在 `metaweave/utils/logger.py` 增加：
  - `set_current_step(step: str) -> None`：设置当前运行 step（全局）。
  - `get_current_step() -> str`：读取当前运行 step（可选，仅用于 Filter）。
- 注意：`MetadataGenerator` 使用 `ThreadPoolExecutor` 并行处理；使用“进程内全局变量”可让所有线程共享同一 step（无需额外传递上下文）。

### 2) 增加日志 Filter：按 step 放行
- 在 `metaweave/utils/logger.py` 增加可被 `logging.config.dictConfig` 引用的 Filter 类：
  - `StepFilter(allowed_steps: list[str])`
  - `filter(record)`：当 `current_step` 在 `allowed_steps` 内才返回 `True`。
- step 字段注入（全局一次，避免每个 handler 重复注入）：
  - 在 `setup_metaweave_logging()` 里安装 `logging.setLogRecordFactory(...)` 包装器，统一写入 `record.step = current_step`。

### 3) 重写 `configs/logging.yaml`
- console handler 保持原样（不使用 `StepFilter`），确保所有日志实时输出到终端。
- 新增 RotatingFileHandler：
  - `ddl_file` → `logs/ddl.log`（filter: `StepFilter(['ddl'])`）
  - `json_file` → `logs/json.log`（filter: `StepFilter(['json','json_llm'])`）
  - `md_file` → `logs/md.log`（filter: `StepFilter(['md'])`）
  - `rel_file` → `logs/rel.log`（filter: `StepFilter(['rel','rel_llm'])`）
  - `cql_file` → `logs/cql.log`（filter: `StepFilter(['cql','cql_llm'])`）
  - `all_file` → `logs/all.log`（filter: `StepFilter(['all'])`）
- formatter 统一显示 step（方案1：所有日志文件/console 都显示 step）：
  - `format: '%(asctime)s - %(name)s - [%(step)s] - %(levelname)s - %(message)s'`
- `%(step)s` 由 LogRecordFactory 全局注入，handlers 无需额外注入 filter。
- 保留 loader 相关 handler（`loader_file`）与其 logger 路由不变。
- 移除/替换旧的 `metadata_file/relationships_file/cql_generator_file` 路由，避免重复写入与混写。
- 采用统一入口 logger（推荐 `metaweave` 或 root）挂载上述 handlers；确保大多数 `metaweave.*` 日志都会经过 step 路由。
  - loader 额外建议：`metaweave.loader.propagate: false`，确保 loader 日志只写入 `loader.log`，不向上级 logger 传播。

### 4) CLI 注入 step（核心触发点）
- 在 `metaweave/cli/metadata_cli.py`：
  - 根据用户 `--step`，在进入对应执行分支前调用 `set_current_step(step.lower())`。
  - `json_llm` 分支需设置 step 为 `json_llm`（路由到 `logs/json.log`）。
    - 注意：`json_llm` 内部会调用 `generator.generate(step="json")`；不需要在内部切换 step，保持 `current_step='json_llm'` 不变即可。
    - 依赖点：`json.log` 的 handler filter 需要覆盖 `StepFilter(['json','json_llm'])`，保证 `json` 与 `json_llm` 都能写入同一文件。
  - `rel_llm` 分支设置 step 为 `rel_llm`（路由到 `logs/rel.log`）。
  - `cql_llm` 分支设置 step 为 `cql_llm`（路由到 `logs/cql.log`）。
  - `all` 设置 step 为 `all`（路由到 `logs/all.log`）。

## 需要修改的文件清单
- `metaweave/utils/logger.py`
  - 增加 step 上下文读写函数
  - 增加 `StepFilter`（供 `dictConfig` 引用）
  - 在 `setup_metaweave_logging()` 中安装 LogRecordFactory（注入 `record.step`）
- `configs/logging.yaml`
  - 新增 step 对应 handlers + filters
  - 调整 logger/handler 绑定（保留 loader 不变）
- `metaweave/cli/metadata_cli.py`
  - 在各 step 分支执行前调用 `set_current_step(...)`

## 验收标准
- 运行以下命令后，仅对应文件产生新增日志内容：
  - `metaweave metadata --step ddl` → `logs/ddl.log`
  - `metaweave metadata --step json` → `logs/json.log`
  - `metaweave metadata --step json_llm` → `logs/json.log`
  - `metaweave metadata --step md` → `logs/md.log`
  - `metaweave metadata --step rel` → `logs/rel.log`
  - `metaweave metadata --step rel_llm` → `logs/rel.log`
  - `metaweave metadata --step cql` → `logs/cql.log`
  - `metaweave metadata --step cql_llm` → `logs/cql.log`
  - `metaweave metadata --step all` → `logs/all.log`
- `metaweave load ...` 仍写入原有 `logs/loader.log`。

## 不在本次范围
- 不对历史日志文件改名/迁移/清理（如 `relationships.log.1`）。
- 不实现 `--step all` 的“按阶段拆分到多个文件”（后续若需要再重构执行流程）。
