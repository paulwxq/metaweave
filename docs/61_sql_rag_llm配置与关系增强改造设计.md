# SQL RAG LLM 配置与关系增强改造设计

> **版本说明**：本文档基于 63\_模块级LLM深合并配置改造 完成后的代码状态进行了修订。
> 标注 `[已完成]` 的章节表示相关实现已经落地，保留用于参考；标注 `[待实施]` 的章节为剩余改造点。

## 1. 背景

基于最新测试场景，我们验证了以下改造方向对 `sql-rag` 样例 SQL 质量有明显提升：

1. 生成阶段仍然按照当前正式逻辑，按 `db_domains.yaml` 中的业务域逐个生成。
2. 在每个 domain 的提示词中，除了当前 domain 下所有表的 Markdown 表结构，还补充这些表在 `output/rel/*.relationships_global.md` 中涉及的关系段落。
3. 在提示词中显式告诉 LLM：当前产物是"训练 SQL 数据"，需要站在业务 domain 的立场设计高代表性的问答对，并保证 question 与 SQL 可以一一对应。
4. 生成使用更适合该场景的模型配置，不再被全局 `llm` 配置完全绑定。

测试结果表明，基于上述方案生成的测试文件 `output/sql/qs_highway_db_pair_test.json` 在 `EXPLAIN` 校验阶段达到 `21/21` 全部通过，成功率 `100%`。这说明该方向具备进入正式模块改造的价值。

---

## 2. 改造目标

本次改造目标有三项：

### 2.1 `[已完成]` 为 `sql_rag` 增加独立 LLM 配置覆盖能力

`sql_rag.llm` 已接入统一解析器 `resolve_module_llm_config()`，在以下三个入口均已生效：

- `metaweave/cli/sql_rag_cli.py` — `generate`、`validate` 命令
- `metaweave/cli/pipeline_cli.py` — `_step_sql_rag_generate()`

配置语义与其他模块完全一致，采用"完整 llm 结构的深合并补丁"，不再需要自定义合成函数。

### 2.2 `[待实施]` 在 SQL 生成提示词中注入关系信息

在当前"按 domain 组织 prompt"的基础上，增加当前 domain 表所涉及的 `rel` 关系段落，作为 JOIN 和业务语义的重要参考。

### 2.3 `[待实施]` 升级样例 SQL 提示词

将现有偏通用的 Question-SQL 提示词升级为"训练数据导向"的版本，使其更强调：

- 业务代表性
- question 与 SQL 的直接对应关系
- SQL 可执行性
- 对表结构与关系信息的严格遵守

---

## 3. 当前现状

### 3.1 `[已完成]` LLM 配置覆盖

当前 `sql-rag` 生成和验证阶段均通过统一解析器 `resolve_module_llm_config()` 获取 LLM 配置：

```python
from metaweave.services.llm_config_resolver import resolve_module_llm_config

llm_config = resolve_module_llm_config(main_config, "sql_rag.llm")
llm_service = LLMService(llm_config)
```

若未配置 `sql_rag.llm`，自动回退到全局 `llm`。

### 3.2 `[未改动]` 当前生成上下文只有 MD

当前 `QuestionSQLGenerator.generate()` 只接收：

- `domains_config_path`
- `md_dir`

不会读取 `rel_directory`，也不会将关系信息注入 prompt。

### 3.3 `[未改动]` 当前生成逻辑已经是"按 domain 逐个生成"

这一点在现有正式代码中已经成立：

1. 读取 `db_domains.yaml`
2. 遍历每个 domain
3. 获取该 domain 的 `tables`
4. 收集对应表的 MD 内容
5. 对每个 domain 发起一次 LLM 调用

因此本次改造不需要改变 `sql-rag` 的基本生成粒度，只需要增强每个 domain 的上下文。

---

## 4. 设计原则

### 4.1 不破坏现有调用方式

现有以下入口都必须继续可用：

- `python -m metaweave.cli.main sql-rag generate`
- `python -m metaweave.cli.main pipeline generate`

如果未配置 `sql_rag.llm`，则行为应与当前保持一致，回退到全局 `llm`。

### 4.2 关系注入尽量复用现有逻辑

不重新设计新的关系筛选算法，而是优先复用 `SQLValidator` 中已有的 `_extract_relevant_relationships()` 逻辑，保持行为一致、改动最小。

> **已知限制**：当前关系筛选函数将输入表名统一压成"纯表名"再匹配标题行（如 `orders`、`customers`）。在单 schema 场景下问题不大，但若存在多 schema 同名表（如 `public.orders` 和 `ods.orders`），可能误召回不相关的关系段落。
>
> 正式实施时，建议将共享函数升级为"优先按完整限定名（schema.table）匹配，找不到时再退化到纯表名"，并在函数文档中注明此限制。

### 4.3 `[已完成]` 配置语义统一

`sql_rag.llm` 已接入统一解析器，与 `domain_generation.llm`、`relationships.llm`、`json_llm.llm`、`comment_generation.llm` 使用相同的深合并语义。不存在"局部覆盖 + 运行时合成"的自定义路径。

---

## 5. `[已完成]` 配置改造设计

### 5.1 配置结构

`sql_rag.llm` 采用与其他模块完全一致的统一深合并语义。标准写法为：

```yaml
sql_rag:
  llm:
    # 可选：切换到不同 provider
    active: qwen
    providers:
      qwen:
        model: qwen-max
        timeout: 120
        extra_params:
          enable_thinking: false
    # 可选：覆盖批量/重试参数
    # batch_size: 10
    # retry_times: 3
  generation:
    questions_per_domain: 10
    uncategorized_questions: 3
    skip_uncategorized: false
    output_dir: "output/sql"
    # Prompt 长度安全截断阈值（由于字符到 token 转换率不稳定，此值仅作工程近似的粗略防爆，非精确 Token 控制）
    max_prompt_chars: 100000
  validation:
    sql_validation_max_concurrent: 5
    timeout: 30
    sql_validation_readonly: true
    sql_validation_max_retries: 2
    enable_sql_repair: true
    repair_batch_size: 1
```

### 5.2 字段语义

`sql_rag.llm` 支持与全局 `llm` 完全相同的顶层字段，包括：

| 字段 | 说明 |
|---|---|
| `active` | 覆盖激活的 provider |
| `providers` | 按 provider 名 覆盖模型、超时、温度等参数 |
| `batch_size` | 覆盖异步批量大小 |
| `retry_times` | 覆盖重试次数 |
| `retry_delay` | 覆盖重试间隔 |
| `langchain_config` | 覆盖异步、并发、SDK 重试等配置 |

未显式覆盖的字段自动继承全局 `llm` 的值（深合并语义）。

### 5.3 运行时解析

通过统一解析器完成，无需自定义合成函数：

```python
from metaweave.services.llm_config_resolver import resolve_module_llm_config

llm_config = resolve_module_llm_config(full_config, "sql_rag.llm")
# llm_config 已经是完整的、可直接传给 LLMService 的 dict
```

---

## 6. `[待实施]` 关系信息注入设计

### 6.1 输入来源

关系信息来自：

- `output/rel/{db_name}.relationships_global.md`

优先使用 `.md` 而不是 `.json`，原因是：

1. 当前正式 `SQLValidator` 已对 `.md` 做了关系段提取逻辑
2. `.md` 更适合作为提示词直接注入
3. 可以避免重新设计 JSON 到自然语言摘要的转换

### 6.2 关系筛选策略

建议提取 `SQLValidator._extract_relevant_relationships(table_names, db_name)` 的核心思路，抽离为共享函数并顺手增强匹配规则，而不是直接物理依赖该私有方法。

提取后的行为可概括为：

1. 打开 `relationships_global.md`
2. 以 `### ` 为段落边界
3. 增强匹配：优先提取完整的 `schema.table.` 片段来精确匹配标题，而不是只用纯表名。**匹配判定仅应发生在每一段的标题行，绝对不可扫描大段正文，以防把正文提及时的话语误认**。

> **已知限制**：原版按纯表名匹配标题的策略对多 schema / 同名表不稳，容易误召回。
> 正式实施的共享函数需升级为准确的"多级别回退匹配"。

### 6.3 复用方式

推荐方案：

- 将 `SQLValidator._extract_relevant_relationships()` 中的逻辑抽到 `metaweave/core/sql_rag/` 下的共享辅助函数
- 例如新增 `context_utils.py`

候选函数：

```python
def extract_relevant_relationship_sections(
    rel_dir: Path,
    table_names: list[str],  # 建议传入全限定名（db.schema.table 或 schema.table）
    db_name: str,
) -> str:
    ...
```

**匹配逻辑详述**（对齐 `rel_llm` 输出的 `.md` 标题格式）：
- 输入允许传入 `db.schema.table` 或 `schema.table` 格式的全限定名。
- 共享函数内部先去前缀，**统一归一化成 `schema.table`** 格式。
- 然后提取文档的 `### ` 标题，**仅针对标题行本身**按 `schema.table.` 片段进行精准子串匹配（带上后缀点，可防止 `orders` 误匹配 `orders_history`）。不扫描匹配段落正文。
- 完全无法匹配任何段落时，最后再退化到纯表名匹配（防脱靶兜底）。

然后：

- `QuestionSQLGenerator` 调它来构造生成提示词
- `SQLValidator` 调它来构造修复提示词

### 为什么不建议直接让 `QuestionSQLGenerator` 调用 `SQLValidator` 私有方法

虽然测试阶段这么做是合理的，但正式代码不建议出现：

- 生成器依赖验证器
- 调用私有方法 `_extract_relevant_relationships`

原因：

1. 职责方向不自然
2. 私有方法语义不稳定
3. 不利于后续维护与单元测试

因此正式改造建议是"抽共享函数"，而不是"直接复用私有方法本身"。

---

## 7. `[待实施]` Prompt 改造设计

### 7.1 当前 Prompt 的问题

当前 `sql-rag` 生成提示词存在以下问题：

1. 只给 MD，不给关系信息，JOIN 容易猜错。
2. 没有明确强调"训练数据"属性，导致生成结果更像泛化问答，而不是高质量标准样本。
3. 没有明确强调"question 与 SQL 必须能直接对应"。
4. 对 SQL 可执行性约束不够强，容易出现：
   - 不存在字段
   - JOIN 条件臆造
   - 中文别名未加双引号
   - 聚合与分组不匹配

### 7.2 新 Prompt 的核心思路

新的 Prompt 需要同时强调三层语义：

#### 第一层：业务域视角

明确告诉 LLM：

- 当前是某个业务 domain
- 生成的问题应该是这个业务域"经常使用"的问题
- 不要只生成技术性 SQL

#### 第二层：训练数据视角

明确告诉 LLM：

- 这是用于训练 Text-to-SQL 的标准样本
- question 与 SQL 必须是强对应关系
- SQL 的执行结果必须能回答 question

#### 第三层：结构约束视角

明确告诉 LLM：

- 表结构只能来自 MD
- JOIN 应优先参考 REL
- 没有明确关系时宁可生成高质量单表 SQL，也不要乱 JOIN

### 7.3 建议的 Prompt 结构

建议将当前 `prompts.py` 中的用户提示词升级为如下结构：

```text
## 数据库背景
{database_description}

## 当前业务主题
主题名称：{domain_name}
主题描述：{domain_description}

## 当前主题包含的表结构文档
{md_content}

## 当前主题相关的表间关系
{rel_content}

## 生成目标
请基于以上资料，生成 {questions_per_domain} 组高质量、可用于训练文本到 SQL 的标准 question/sql 对。

## 训练样本要求
1. 使用 PostgreSQL 语法。
2. 问题使用中文，SQL 中表名和字段名必须使用真实英文名。
3. 查询结果列可使用中文别名，但别名必须用双引号包裹。
4. 生成的样例要有业务代表性，优先覆盖经营分析、趋势分析、排行分析、结构占比、跨表关联分析、明细定位等常见业务场景。
5. 如果表间关系信息中出现了可用关联，请优先参考这些关系设计 JOIN，避免臆造关联字段。
6. 如果关系文档中没有明确给出某些表的关联关系，不要强行 JOIN。
7. SQL 必须可执行，避免引用不存在的字段、表、别名或聚合错误。
8. 每条 SQL 必须是单行文本，并且以分号结尾。
9. question 与 SQL 必须直接对应，SQL 的执行结果应能回答问题。
10. 所有问题和 SQL 都必须严格基于提供的表结构和关系信息，不要虚构新表、新字段。

## 输出格式
[
  {"question": "问题文本", "sql": "SELECT ...;"},
  ...
]
```

### 7.4 System Prompt 建议

当前 system prompt 偏弱，建议升级为更明确的版本：

```text
你是一位精通 PostgreSQL 和业务分析的资深数据分析师。你正在为 Text-to-SQL 训练集生成高质量标准样本。请严格依据给定的业务域背景、表结构文档和表间关系信息设计问题与 SQL。你输出的每一条 SQL 都必须可执行、语义准确，并且其查询结果能够直接回答对应的问题。
```

### 7.5 `rel_content` 为空时的占位文案

当 `rel` 文件不存在或当前 domain 的表没有匹配到任何关系段落时，`{rel_content}` 应使用以下固定占位文案，而非空字符串：

```text
未提取到与当前主题表相关的关系段落，可仅依据表结构生成高质量单表或谨慎关联的 SQL。
```

这样 LLM 能明确感知到"不是遗漏了关系信息，而是确实没有"，避免自行臆造 JOIN。

---

## 8. `[部分完成]` 剩余代码改造点

### 8.1 `[已完成]` `configs/metadata_config.yaml`

`sql_rag.llm` 配置段已存在，采用统一深合并语义。

### 8.2 `[待实施]` `metaweave/core/sql_rag/generator.py`

建议改动：

1. 新增 `rel_dir` 输入支持
2. 新增关系上下文构造逻辑（调用共享函数）
3. 升级 prompt 模板变量（新增 `{rel_content}`）

建议的接口变化：

```python
def generate(
    self,
    domains_config_path: str,
    md_dir: str,
    rel_dir: Optional[str] = None,
) -> GenerationResult:
```

说明：

- `rel_dir` 设为可选，保证旧调用兼容
- 未传时退化为占位文案（见第 7.5 节）

### 8.3 `[待实施]` `metaweave/core/sql_rag/prompts.py`

改动：

- 升级 `SYSTEM_PROMPT`
- 升级 `USER_PROMPT_TEMPLATE`
- 新增 `{rel_content}` 变量

### 8.4 `[已完成]` `metaweave/cli/sql_rag_cli.py`

LLM 配置已通过 `resolve_module_llm_config(main_config, "sql_rag.llm")` 接入。

剩余改动：

- `[待实施]` 将 `rel_directory` 传给生成器（从 `output.rel_directory` 推导，不必新增 CLI 参数）

### 8.5 `[已完成]` `metaweave/cli/pipeline_cli.py`

LLM 配置已通过 `resolve_module_llm_config(ctx.loaded_config, "sql_rag.llm")` 接入。

剩余改动：

- `[待实施]` 在 `_step_sql_rag_generate()` 中将 `rel_dir` 传给生成器

### 8.6 `[待实施]` `metaweave/core/sql_rag/context_utils.py`（新建）

将 `SQLValidator._extract_relevant_relationships()` 的逻辑抽取为共享函数，供生成器和验证器共同使用。

---

## 9. 兼容性设计

### 9.1 向后兼容

若用户未配置 `sql_rag.llm`：

- 仍使用全局 `llm`（统一解析器自动回退）
- 生成行为与当前版本兼容

若 `rel` 文件不存在：

- 不阻断生成
- 在 prompt 中使用固定占位文案："未提取到与当前主题表相关的关系段落，可仅依据表结构生成高质量单表或谨慎关联的 SQL。"

### 9.2 与现有验证模块的一致性

生成与修复阶段都参考同一套关系段落筛选逻辑（共享函数），有助于：

- 降低生成与修复对关系理解不一致的问题
- 减少维护成本

---

## 10. 风险与注意事项

### 10.1 Prompt 长度预算控制

> [!IMPORTANT]
> 加入 `rel_content` 后，prompt 长度会增加。这在表多、字段多的 domain 下可能导致 token 成本飙升、模型截断、后半段关系信息被吃掉，反而降低生成稳定性。

**实现要求**（不可延后）：

1. **先保留所有表的标题和字段摘要**——作为生成正确 SQL 的根基，**最低保留集必须写死为：`列名 + 数据类型 + 主外键/约束/索引信息`**。样例值、长注释、扩展说明处于最高裁剪优先级。
2. **关系段最多保留前 N 段或前 X 字符**——超预算时优先裁剪关系段内的注释/样例值，不裁剪列名和关系结构。
3. **在配置文件中显式读取 `sql_rag.generation.max_prompt_chars` 配置**（如 100000。需明确：鉴于字符与 token 的转换密度极不稳定，此阈值仅作为工程上的“粗略防爆”近似值，不可用作严格的滑动窗口控制）。
4. **系统级完整裁剪闭环链路**：
   - 第一阶段：全文 MD 常规拼接
   - 第二阶段：如超限 -> 精简 MD（砍掉字段级的长注释与样例值）
   - 第三阶段：如仍超限 -> 对 `rel_content` 关系段进行硬截断（只保留前 N 个匹配到的关系声明）
   - 第四阶段：如仍不足 -> 按表顺序截断非核心说明文本，**但底线是绝对不得删除最低保留集（列名+类型+约束信息）**。即使文本突破阈值，这部分硬核信息也必须全量注入 Prompt。

### 10.2 关系段误召回

当前按标题匹配表名的方式较粗，可能把一些边缘相关段落也带进来。

但从测试结果看，这种误召回的负面影响可接受，且明显优于完全不给关系信息。

> **已知限制**：关系筛选共享函数当前仅对单 schema 场景充分稳健。多 schema 下需优先按完整限定名（schema.table）匹配，找不到时再退化到纯表名。

### 10.3 `[已完成]` 局部 LLM 覆盖语义统一

所有模块级 LLM 配置均已统一接入 `resolve_module_llm_config()`，采用深合并语义：

- `domain_generation.llm`
- `sql_rag.llm`
- `relationships.llm`
- `json_llm.llm`
- `comment_generation.llm`

无需额外处理。

---

## 11. 实施步骤建议

建议按以下顺序落地剩余改造：

1. ~~配置层：在 `metadata_config.yaml` 中增加 `sql_rag.llm`~~ `[已完成]`
2. 公共能力层：
   将关系段提取逻辑抽成共享函数 `context_utils.py`
3. 生成器层：
   给 `QuestionSQLGenerator` 增加 `rel_dir` 支持
4. Prompt 层：
   升级 system/user prompt，引入 `{rel_content}` 和占位文案
5. ~~CLI / Pipeline 层：接入 `sql_rag.llm` 配置覆盖~~ `[已完成]`
   剩余：在 CLI/Pipeline 中将 `rel_dir` 传给生成器
6. Prompt 预算控制：
   在 `generator.py` 中实现长度裁剪策略
7. 测试层：
   将已验证有效的测试场景补充为正式集成测试或回归测试

---

## 12. 预期收益

完成本次改造后，`sql-rag` 将具备以下收益：

1. 可为 SQL 训练数据生成单独选模
2. JOIN 更可靠，错误字段更少
3. 样例 SQL 更贴近业务域的真实使用场景
4. question 与 SQL 的对应关系更直接，更适合训练 Text-to-SQL
5. 与验证阶段共享关系理解逻辑，整体链路更一致

---

## 13. 结论

本次改造属于"低到中等风险、收益明确"的增强型改造。

其中：

- ~~`sql_rag.llm` 是配置能力增强~~ `[已完成]`
- `rel` 注入是上下文增强 `[待实施]`
- prompt 升级是产物质量增强 `[待实施]`

三者叠加后，可以将当前 `sql-rag` 从"基于表结构的通用 SQL 生成"提升为"基于业务域、表结构和关系信息的训练数据生成模块"，这与项目后续面向 NL2SQL 训练样本沉淀的目标是高度一致的。
