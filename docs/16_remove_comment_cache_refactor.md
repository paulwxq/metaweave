# 16_ 删除 Comment Cache（comment_cache.json）功能改造规划

## 目标

- 从代码中**完全删除**基于 `cache/comment_cache.json` 的注释缓存能力（不考虑兼容性）。
- 注释的“缓存/沉淀”仅依赖显式产物：
  - `output/ddl/*.sql`（包含表/字段注释）
  - `output/json/*.json`（json / json_llm 的产物，包含表/字段注释）

## 非目标

- 不改动 DDL/JSON 的数据结构（除非为了删除 cache 相关字段/配置引用必须改）。
- 不讨论 LLM Prompt、注释质量策略优化。

## 现状与问题（为什么删）

- 当前 cache key 仅到 `schema.table` 级别（`table:{schema}.{table}` / `columns:{schema}.{table}`），**不包含表结构指纹**：
  - 表结构变化时，cache 可能复用过期注释，甚至导致新列注释永远不生成（columns cache 命中后直接返回整表 dict）。
- 产物（DDL/JSON）本身已可作为“可见、可追溯”的缓存载体，`comment_cache.json` 反而引入第二份隐式状态与排障成本。
- cache 文件为共享写入点，未来并发/多进程存在竞争风险（损坏/丢写）。

## 影响范围（必须修改的代码点）

### A) CacheService（删除模块）

- 删除文件：`metaweave/services/cache_service.py`
- 更新导出：`metaweave/services/__init__.py` 移除 `CacheService`。

### B) CommentGenerator（删除缓存参数与逻辑）

文件：`metaweave/core/metadata/comment_generator.py`

- 构造函数签名调整：
  - 删除参数：`cache_service`, `cache_enabled`
  - 删除字段：`self.cache_service`, `self.cache_enabled`
- 删除所有缓存读写逻辑：
  - `generate_table_comment()` 中的 `cache_key`、`get()`、`set()`
  - `generate_column_comments()` 中的 `cache_key`、`get()`、`set()`
- 日志文案移除“缓存启用/禁用”的描述。

### C) MetadataGenerator（移除 cache 初始化与传递）

文件：`metaweave/core/metadata/generator.py`

- `_init_components()`：
  - 删除 `CacheService` 初始化与 `cache_file`/`cache_enabled` 的读取
  - `CommentGenerator(...)` 改为只传 `llm_service`
- 移除对 `CacheService` 的 import。

### D) JsonLlmEnhancer（移除 cache 配置与读写逻辑）

文件：`metaweave/core/metadata/json_llm_enhancer.py`

- `__init__()`：
  - 删除 `cache_enabled/cache_file/cache_service` 初始化与相关配置读取
- 删除方法与调用：
  - 删除 `_apply_cached_comments()` 及其调用点
  - 删除 `_update_comment_cache()` 及其调用点
- 逻辑调整：
  - `comment_needs` 的分析仍然保留（决定是否需要“注释补全”类的 LLM 调用）
  - 删除 `_apply_cached_comments()` 后，`comment_needs` 直接决定是否调用 LLM（不再存在“先用 cache 补齐再判断”的中间步骤）
  - 注释结果只写回 `output/json/*.json`（当前已原地写回，保留即可）
  - `comment_generation.overwrite_existing` 语义不变：为 `true` 时强制覆盖已有注释；删除 cache 后不再有“cache 命中导致跳过 LLM 从而未覆盖”的路径（token 成本会更可预期地上升）

### E) 配置文件（删除 cache 配置项）

不考虑兼容性：删除配置项而不是保留默认值。

- `configs/metadata_config.yaml`
  - 删除：`comment_generation.cache_enabled`
  - 删除：`comment_generation.cache_file`
- `configs/config.yaml`（如仍在使用 comment_generation）
  - 删除：`comment_generation.cache_enabled`
  - 删除：`comment_generation.cache_file`

### F) 文档（同步移除 cache 说明）

目标：避免用户继续看到 cache 的概念，减少误用。

- `metaweave/README.md`：删除 comment_generation 下 cache 相关说明
- `CLAUDE.md`：删除 “LLM Integration” 中关于 `cache/comment_cache.json` 的描述
- 其他涉及 `comment_cache.json` 的 docs 逐步清理（按 `grep comment_cache` 列表处理）

### G) 测试（如存在相关用例则更新/删除）

- 检查 `tests/` 中是否存在：
  - 直接测试 `CacheService` 的用例（应删除或改为产物驱动的测试）
  - 依赖 `comment_generation.cache_enabled/cache_file` 的测试配置（需更新）

## 行为变化（删除后的预期）

- `--step ddl` / `--step md`
  - 缺注释时直接调用 LLM 生成（不再尝试复用历史 cache）
  - 注释沉淀由产物承担：DDL/MD 输出中携带的注释即“可追溯结果”
- `--step json_llm`
  - 不再在增强前“先用 cache 补齐注释”
  - 不再把增强结果写回 cache
  - 只把最终注释写回 JSON 文件

## 风险与注意事项

- 成本变化：重复运行时缺注释会重复调用 LLM（token/时间增加），但换来状态收敛与可复现性提升。
- 注释稳定性：LLM 输出存在随机性，同一张表在不同时间运行可能得到措辞不同的注释；如需更稳定/可重复的注释，可考虑将注释写回数据库（后续运行优先复用数据库注释）。
- 依赖检查：确认没有其他模块 import/use `CacheService`（需全局搜索）。
- 删除 cache 后，`cache/` 目录可能不再自动创建；如有脚本/文档依赖该目录，需要同步调整。

## 实施步骤（建议顺序）

1. 全局搜索 `CacheService` 与 `cache_enabled/cache_file/comment_cache.json`，确认仅上述文件引用。
   - 同时检查 `tests/`、`CLAUDE.md` 是否有相关引用需要同步删除/更新
2. 改造 `CommentGenerator`：移除参数与缓存逻辑，确保功能仅依赖 LLM 返回。
3. 改造 `MetadataGenerator`：移除 cache 初始化与向 `CommentGenerator` 传递 cache。
4. 改造 `JsonLlmEnhancer`：移除 cache 读写方法与相关分支。
5. 删除 `metaweave/services/cache_service.py` 与 `services/__init__.py` 导出项。
6. 清理配置文件的 cache 配置项。
6.5. 验证代码可正常导入（无 import 错误）：
    - `python -c "from metaweave.core.metadata.generator import MetadataGenerator"`
    - `python -c "from metaweave.core.metadata.comment_generator import CommentGenerator"`
    - `python -c "from metaweave.core.metadata.json_llm_enhancer import JsonLlmEnhancer"`
    - `uv run metaweave --help`
    - `python -m metaweave.cli.main --help`
7. 运行最小验证（见下一节）。

## 验证清单（建议）

- `metaweave metadata --config configs/metadata_config.yaml --step ddl`
  - 缺注释时仍能生成注释（LLM 正常调用）
  - 不产生/不读取 `cache/comment_cache.json`
- `metaweave metadata --config configs/metadata_config.yaml --step md`
  - md 仍可生成（并且不依赖 cache）
- `metaweave metadata --config configs/metadata_config.yaml --step json_llm`
  - 阶段2增强仍可运行（不依赖 cache）
  - 仅更新 JSON 文件，不写 cache 文件

## 升级迁移（破坏性变更）

### 配置文件调整

删除以下配置项（不再支持）：

```yaml
comment_generation:
  cache_enabled: true                     # ← 删除
  cache_file: cache/comment_cache.json    # ← 删除
```

### cache 文件处理

- 现有的 `cache/comment_cache.json` 将不再被读取，可手动删除。
- 如有脚本/文档依赖 `cache/` 目录，需要同步更新（删除依赖或改为依赖 `output/` 产物目录）。
