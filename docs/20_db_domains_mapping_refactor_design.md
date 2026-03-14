# 业务主题（Domain）映射机制重构设计方案

## 1. 背景与目标

当前系统中，表与业务主题（Domain）的分配逻辑存在于废弃的 `llm_json_generator.py` 中，且是在生成 JSON 时对每张表单独调用 LLM 进行推断。这导致了几个问题：
1. Token 消耗大且效率低下（分表推断）。
2. 新版 `json_llm` (`JsonLlmEnhancer`) 缺失了该功能的迁移，导致链路断裂，知识图谱中 Domain 为空。
3. 缺乏全局视角的宏观映射，难以进行人工审查和微调。

**本设计的核心目标**是将“业务主题推断”与“元数据 JSON 生成”解耦：
* **控制面**：在生成 `db_domains.yaml` 时，利用 LLM 一次性完成 Domain 的定义与表的分配映射。
* **数据面**：在生成 JSON 时，仅作为一个纯粹的“读取与注入”动作，彻底告别单表 LLM 推断 Domain 的模式。

## 2. 核心改造点设计

### 2.1 `db_domains.yaml` 结构升级（增加表映射）
要求在生成 `db_domains.yaml` 时，让 LLM 将输入的表名（三段式：`db.schema.table`）分配到对应的 Domain 下。

**`_未分类_` 主题的表分配策略**：
- LLM prompt 中明确要求：**无法归入任何业务主题的表，放入 `_未分类_`**。
- `_未分类_` 是系统预置的特殊主题，LLM 不负责创建它（由 `_normalize_domains` 自动注入），但 LLM **可以向其分配表**。
- 代码层面：`_normalize_domains` 仍然过滤掉 LLM 返回的 `_未分类_` domain 定义（防止 description 被覆盖），但需要**保留 LLM 为 `_未分类_` 分配的 tables 列表**，并合并到系统预置的 `_未分类_` 条目中。
- 这与 JSON 注入阶段的语义形成闭环：`table_domains: ["_未分类_"]` 表示经模型评估后明确无法归类；`table_domains: []` 表示该表未参与 Domain 生成（无 YAML 或该表未出现在任何 domain 中）。

**修改后的 YAML 结构示例：**
```yaml
# configs/db_domains.yaml
database:
  name: SakilaRental
  description: ...
llm_inference:
  max_domains_per_table: 3
domains:
  - name: _未分类_
    description: 无法归入其他业务主题的表
    tables:
      - SakilaRental.public.some_legacy_table
  - name: 租赁业务流程
    description: 完整记录租赁事件...
    tables:
      - SakilaRental.public.rental
      - SakilaRental.public.payment
  - name: 影片资产与元数据
    description: ...
    tables:
      - SakilaRental.public.film
```

### 2.2 JSON 生成阶段的 Domain 注入（零 LLM 调用）
*现状澄清：当前生效的新版 `JsonLlmEnhancer` 没有任何 Domain 相关的逻辑（仅处理表分类和注释）。历史带有 Domain 推断逻辑的 `LLMJsonGenerator` 已被废弃。*

**注入时机说明**：Domain 注入将**完全放置在 `--step json`（基础 JSON 生成）阶段**完成（具体在 `MetadataProfiler` 构建表画像时）。
由于 `--step json_llm` 的架构是在全量基础 JSON 上进行原地增强，因此只要基础阶段注入完成，`json_llm` 自然会继承该属性，无需在增强器中处理任何 Domain 逻辑。

**触发条件**：在执行 `--step json` 时，**自动检测 `db_domains.yaml` 文件是否存在**。文件存在则加载并注入；文件不存在则静默跳过。不引入额外的配置开关（如 `enabled`），保持最简设计。无需任何额外的 CLI 参数控制，与现有的 `--domain` 参数（用于 `rel_llm` 阶段的 Domain 过滤）职责完全解耦。

在执行 `--step json` 且 `db_domains.yaml` 存在时：
1. **不再调用 LLM 推断 Domain**：该阶段无任何 LLM 调用，Domain 信息完全来自本地 YAML 文件的字典查询。
2. **加载映射字典**：在内存中反转 `db_domains.yaml` 的结构，构建一个 `Table -> List[Domain]` 的查询字典。
3. **精准注入**：对于当前处理的表，从字典中查出其所属的 Domain 列表，并直接赋值给 `table_profile.table_domains`。
4. **兜底策略**：如果在 YAML 中找不到该表，或者 `db_domains.yaml` 文件不存在，则静默赋值为 `[]`（空列表），**不报错、不阻断**，实现优雅降级。（注：`[]` 表示缺乏领域配置信息，而 `_未分类_` 表示经模型评估后明确无法归类的结果，两者在语义上严格区分）。

*注：当前 JSON 的 Schema 已经定义 `table_profile.table_domains` 为 `List[str]`，天然支持一张表属于多个 Domain 的情况，数据结构无需任何改动。*

### 2.3 下游模块 (rel/cql) 的读取与适配
下游操作（关系发现 `rel` / `rel_llm` 和 知识图谱构建 `cql` / `cql_llm`）的**核心读取逻辑保持不变**，它们依然从 `output/json/` 的 JSON 文件中读取 `table_domains` 属性。
但需要配合 2.2 的兜底策略进行**防御性校验的放宽**：取消原本“找不到 Domain 字段即报错阻断”的严格限制。当读取到 `[]` 时，允许模块平滑降级（如退化为不区分 Domain 的全量处理模式），以此实现流程的完美闭环。

### 2.4 MD 上下文文件数量限制的配置化
当前通过 CLI 参数 `--md-context-limit`（默认 100）来控制向 LLM 提交的 MD 摘要文件数量（由于每张表对应一个 MD 文件，这也间接限制了参与 Domain 生成的表数量）。为了更好的工程化管理，将此限制提升到配置文件中。

**说明**：**保留原有的 CLI 参数**，并确立严格的取值优先级。
**参数优先级策略**：`CLI 参数 (--md-context-limit)` > `配置文件 (metadata_config.yaml 的 domain_generation.md_context_limit)` > `代码默认值 (100)`。

**`configs/metadata_config.yaml` 新增配置：**
```yaml
domain_generation:
  md_context_limit: 100  # 从配置文件读取限制，覆盖默认值
```
在不考虑 500+ 表极端情况的当前阶段，通过配置 100-200 的合理阈值，既能保证 LLM 上下文不溢出，又能覆盖大部分中小型数据库。

### 2.5 生成 Domain 的专属 LLM 配置（支持长文本模型）
生成全局映射需要将所有的表名和注释发给 LLM，对上下文窗口（Context Window）要求较高，可能需要使用 `gpt-4o`、`claude-3-5-sonnet` 或 128k/200k 上下文的特定模型。
为了不影响其他短文本任务（如单表注释生成），为 Domain 生成提供独立的 LLM 配置。

**`configs/metadata_config.yaml` 新增配置：**
```yaml
domain_generation:
  llm:
    provider: openai
    model_name: gpt-4o  # 可以单独指定支持长上下文的模型
    api_key: ...
    temperature: 0.1
```
代码实现逻辑：优先读取 `domain_generation.llm`，如果未配置，则降级使用全局的 `llm` 配置。

## 3. 影响评估与风险排查

经过全面的架构评估，本方案的潜在影响和工程考量如下：

1. **对当前 JSON 结构的兼容性**：
   - **完全兼容**。现有 `table_domains` 已是数组结构，完全承载一对多的映射关系。
2. **非阻断性设计（优雅降级）**：
   - 即使 `db_domains.yaml` 为空或损坏，JSON 生成时只回退到空列表 `[]`，严格区分了”未处理/无配置”和”明确未分类”，保障了标准轨道（`ddl -> json -> rel -> cql`）的健壮性。
3. **对完整执行过程（`--step all` / `all_llm`）的影响**：
   - **现状**：`all` 参数的固定顺序是 `ddl -> md -> json(_llm) -> rel(_llm) -> cql`。
   - **决策记录**：由于 `db_domains.yaml` 的生成（`--generate-domains`）目前是一个独立的命令，不在 `all` 的调度环内。**在当前改造版本中，暂不修改 `--step all` 的执行链路**。即：在调度器中自动插入 `generate_domains` 的功能，将作为明确的**下一阶段（后续迭代）**任务，待本次基础的 `db_domains.yaml` 生成模块和映射机制改造彻底稳定后再行实施。目前的独立单步执行（CLI 显式调用）不受任何影响。
4. **表名大小写敏感性问题**：
   - 数据库中的 Schema 和 Table 往往有大小写问题（如 PostgreSQL）。在生成 YAML 和读取 YAML 进行匹配时，**统一采用小写化（或 `casefold()`）匹配方案**：在构建 `Table -> List[Domain]` 反向索引时，将 YAML 中的表名转为小写作为 Key；在查字典时，也将当前表名转为小写后进行匹配。以此彻底规避 LLM 大小写输出不稳定或数据库规范差异导致的 Cache Miss 风险。

## 4. 实施清单

1. **清理历史遗留代码**：
   - 彻底删除已废弃的 `metaweave/core/metadata/llm_json_generator.py`。经全局搜索确认，该文件无任何运行时代码引用（所有引用均在 `docs/` 文档和 `CLAUDE.md` 中，属于历史描述性文字，不影响运行）。
   - 同步删除其对应的测试文件（如 `tests/unit/metaweave/test_llm_json_generator.py`）。
   - 同步更新 `CLAUDE.md` 中对该文件的描述引用。
2. **修改 `configs/metadata_config.yaml`**：新增 `domain_generation` 配置块（2.4 和 2.5 中分别描述的字段属于同一个块），完整结构如下：
   ```yaml
   domain_generation:
     md_context_limit: 100
     llm:
       provider: openai
       model_name: gpt-4o
       api_key: ...
       temperature: 0.1
   ```
3. **修改 `DomainGenerator`**：
   - **完善三段式表名来源**：当前 `output/md` 目录下的文件名已经天然包含了三段式信息（例如 `dvdrental.public.city.md`）。在构建 `_build_md_context` 时，直接提取文件的 `stem` 作为表名提交给 LLM。
   - **升级 LLM 提示词（Prompt）**：明确要求 LLM 将所有输入的表名全部分类到对应的 Domain 中。输出结构从 `{"name": "...", "description": "..."}` 升级为 `{"name": "...", "description": "...", "tables": ["db.schema.table1", "db.schema.table2"]}`。
   - 修改 `_parse_response` 和 `write_to_yaml`，支持 `tables` 数组的解析和持久化写入。
   - **`_未分类_` tables 合并逻辑**：修改 `write_to_yaml` 中的合并流程。当前代码（`domain_generator.py:319-321`）直接过滤掉 LLM 返回的所有 `_未分类_` 条目（包括其 tables）。需要改为：在过滤前提取 LLM 返回的 `_未分类_` 条目中的 `tables` 列表，合并到系统预置的 `_未分类_` 条目中，确保无法归类的表不被丢弃。
   - **初始化改造**：修改 `__init__` 中的 `LLMService` 实例化逻辑。不再直接使用 `config.get("llm", {})`，而是先提取 `config.get("domain_generation", {}).get("llm")`。如果该专属配置存在且有效，则合并或覆盖全局 LLM 参数构建新的 config；如果不存在，则 fallback 回退到全局 `config.get("llm", {})`。以此实现模型的无缝切换。
4. **修改 `MetadataGenerator` (或其依赖的 `MetadataProfiler`)**：
   - **仅在 `--step json` 基础生成阶段**，在生成表画像（`table_profile`）时，读取 `db_domains.yaml` 构建反向索引（构建索引时将 key 统一 `casefold()` 处理，查询时同样对当前表名 `casefold()` 后匹配，参见 3.4 节）。
   - 将匹配到的 Domain 列表赋值给 `table_profile.table_domains`（`json_llm` 将自动继承该属性，无需在 `JsonLlmEnhancer` 中编写任何 Domain 逻辑）。
5. **修改 `LLMRelationshipDiscovery` 等下游防御逻辑**：
   - 放宽对 Domain 的强制校验，即使读取到的 `table_domains` 为空列表 `[]`，也不报错中断，按照不区分 Domain 的标准逻辑（全量或降级）处理。

## 5. 结论与已知风险

该设计将“复杂推断”前置于全局配置生成阶段，将“数据装配”后置于 JSON 解析阶段。这在修复当前 Domain 分配缺失断层的同时，通过本地字典映射实现了 JSON 主题注入过程的零 Token 成本，提升了系统的执行效率和架构合理性。

**已知风险与待确认项（Pending Confirmations）：**
1. **多库/复杂 Schema 场景测试**：三段式命名（db.schema.table）在解析与匹配时，需确保特殊字符或非标准命名的兼容性，避免截断异常。
2. **大模型输出稳定性**：当表数量逼近上限时，LLM 返回的 JSON 可能因输出 token 耗尽而被截断，导致解析失败。应对思路：在 prompt 设计中合理设置 `max_tokens`，并补充异常重试与解析防御逻辑；若单次生成仍不稳定，可考虑两阶段生成策略（先生成 domain 列表，再逐 domain 分配表）作为备选方案。
3. **流程自动化的平滑过渡**：由于 `--step all` 暂不集成自动生成 Domain 的环节，需要在相关文档或 CLI 提示中，引导用户在跑全流程前，先手动执行 `--generate-domains` 以构建配置底座。