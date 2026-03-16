# 55_db_domains 单一事实源改造方案

## 1. 背景

当前项目中，`domain` 信息存在两种设计路径：

1. 作为外部业务配置，存放于 `configs/db_domains.yaml`
2. 作为中间产物字段，写入 `output/json/*.json` 的 `table_profile.table_domains`

从代码实现上看，`json` 步骤曾尝试将 `db_domains.yaml` 反向注入到 JSON 中；但从当前仓库内已有 `output/json/*.json` 实际内容来看，`table_domains` 字段并未稳定出现在产物中。与此同时，`rel_llm` 和 `cql` 的部分逻辑又仍然假定该字段存在。

这带来两个问题：

1. `db_domains.yaml` 手工调整后，需要重跑 `json/json_llm` 才能把修改传递下游，成本过高
2. `domain` 同时存在于 YAML 和 JSON，形成双份事实来源，容易出现不一致

因此，有必要将 `db_domains.yaml` 收敛为 `domain` 的单一事实来源，其他阶段在运行时直接读取该配置，而不是依赖 JSON 中间产物。

## 2. 目标

本次改造目标如下：

1. 取消 `json/json_llm` 向 JSON 产物写入 `table_domains`
2. 将 `configs/db_domains.yaml` 设为唯一 domain 来源
3. `rel_llm` 在执行 `--domain/--cross-domain` 时，直接基于 `db_domains.yaml` 做表分组与过滤
4. `cql/cql_llm` 在生成阶段直接从 `db_domains.yaml` 补充表节点的 `table_domains`
5. 未来如 `table_schema_loader`、`dim_value_loader` 等需要 domain 信息，也应直接读取 `db_domains.yaml`
6. 保留 `output/sql` 这类最终业务产物中保留 domain 的能力，但不再要求中间 JSON 持久化 domain

## 3. 非目标

本次改造不包含以下内容：

1. 不调整 `db_domains.yaml` 的生成逻辑
2. 不改造普通规则版 `rel` 的候选生成与评分逻辑
3. 不为当前尚未消费 domain 的 loader 强行增加 domain 字段
4. 不改变 `dim_tables.yaml` 的职责
5. 不在本次改造中新增复杂缓存机制

## 4. 现状分析

### 4.1 当前 JSON 注入逻辑

当前 `metaweave/core/metadata/generator.py` 中存在如下逻辑：

1. 初始化时读取 `configs/db_domains.yaml`
2. 构建 `db.schema.table -> [domain...]` 的反向索引
3. 在 `json` 阶段把结果写入 `metadata.table_profile.table_domains`

同时，`metaweave/core/metadata/models.py` 的 `TableProfile.to_dict()` 也会把 `table_domains` 序列化进 JSON。

### 4.2 当前下游消费点

#### 4.2.1 rel_llm

`metaweave/core/relationships/llm_relationship_discovery.py` 当前在启用 `--domain` 或 `--cross-domain` 时：

1. 读取 CLI 传入的 `db_domains_config`
2. 但并不直接使用 YAML 中的表清单做分组
3. 实际分组逻辑依赖 `tables[*].table_profile.table_domains`

这意味着：

1. 只有 JSON 中提前写入了 `table_domains`，过滤才可靠
2. 如果 YAML 修改后未重跑 `json`，`rel_llm` 就会使用过期 domain
3. 如果 JSON 根本没有 `table_domains`，则当前过滤结果可能为空或不完整

#### 4.2.2 cql / cql_llm

`metaweave/core/cql_generator/reader.py` 当前从 Step 2 JSON 中读取 `table_profile.table_domains`，再由 `writer.py` 写入 Neo4j `Table` 节点属性 `n.table_domains`。

经代码检索，`metaweave/core/cql_generator/` 目录当前不存在 `db_domains.yaml`、`domains_config` 或等价 domain 配置入口的直接引用；当前 CQL 阶段的 domain 信息仅来自 Step 2 JSON。

这意味着：

1. `cql` 当前并不直接读取 `db_domains.yaml`
2. YAML 修改后若不重跑 `json`，图节点上的 domain 也可能滞后
3. 当前 writer 对空 `table_domains` 的处理偏保守，旧值可能被保留

#### 4.2.3 json_llm

`json_llm` 不是独立生成 domain 的步骤，而是：

1. 先执行 `json`
2. 再由 `json_llm_enhancer.py` 对已有 JSON 原地增强

当前 `json_llm_enhancer.py` 中：

1. 不直接读取 `db_domains.yaml`
2. 不包含专门写入 `table_domains` 的逻辑
3. 对输入 JSON 采用复制后局部改写的方式，主要改动 `table_category`、注释及增强时间戳

因此，`json_llm` 对 domain 的依赖是间接的：

1. 如果上游 `json` 已写入 `table_domains`，`json_llm` 通常会保留该字段
2. 如果上游 `json` 不再写入 `table_domains`，`json_llm` 也将自然不再输出该字段

这意味着本次改造中无需为 `json_llm` 额外设计新的 domain 写入逻辑，但需要在消费方侧消除对 `table_domains` 的依赖。

#### 4.2.4 table_schema_loader / dim_value_loader

当前这两个 loader 并未消费 `domain`：

1. `table_schema_loader` 当前只使用 MD、JSON 中的 `table_category`、时间列提示等信息
2. `dim_value_loader` 仅依赖 `dim_tables.yaml` 和数据库查询

因此，本次改造不会对现有 loader 主流程造成直接影响。

#### 4.2.5 sql_rag

`sql_rag` 已经直接读取 `configs/db_domains.yaml`，这与目标架构一致，可作为参考实现方向。

## 5. 总体设计

### 5.1 设计原则

1. `db_domains.yaml` 是唯一事实来源
2. JSON 是通用元数据产物，不承载易变的业务编排信息
3. 需要 domain 的阶段在运行时解析 YAML
4. 中间产物尽量避免因配置微调而整体重算

### 5.2 目标架构

建议新增一个统一的 domain 解析组件，例如：

- `metaweave/core/domains/resolver.py`

该组件负责：

1. 加载 `configs/db_domains.yaml`
2. 标准化表名格式，统一为 `database.schema.table`
3. 提供表到 domain 的反查接口
4. 提供按 domain 获取表集合的接口
5. 提供 `--domain` / `--cross-domain` 所需的表对生成辅助能力

路径策略约束如下：

1. `DomainResolver.__init__` 必须接收显式 `domains_config_path`
2. `DomainResolver` 内部不硬编码 `get_project_root() / "configs" / "db_domains.yaml"`
3. 默认路径的决定权由调用方负责：
   - CLI 场景由 `--domains-config` 传入
   - 非 CLI 场景由上层 generator / service 显式传入

建议将接口分为三类。

核心接口：

1. `get_domains_for_full_name(full_table_name: str) -> List[str]`
2. `get_tables_for_domain(domain_name: str) -> List[str]`
3. `get_all_domains() -> List[str]`
4. `build_domain_table_map() -> Dict[str, List[str]]`

便捷接口：

1. `normalize_table_name(name: str, db_name: str | None = None) -> str`
2. `get_domains_for_schema_table(schema_table_name: str, db_name: str) -> List[str]`

业务辅助接口：

1. `resolve_table_pairs(domain, cross_domain, available_tables) -> List[Tuple[str, str]]`

其中：

1. `full_table_name` 统一采用 `database.schema.table`
2. 对大小写使用 `casefold()` 归一
3. 对 YAML 中不存在的表返回空列表，而不是抛错
4. `get_domains_for_schema_table("public.orders", db_name="dvdrental")` 内部应复用统一标准化逻辑，而不是让调用方自行拼接
5. 对于不属于任何 domain 的表，resolver 返回 `[]`
6. `resolver` 不自动补 `["_未分类_"]`，`_未分类_` 的业务解释交由上层决定

阶段建议：

1. 阶段 1 必须完成核心接口
2. 便捷接口可随首批调用方需要实现
3. `resolve_table_pairs()` 建议在 `rel_llm` 改造时同步落地

## 6. 具体改动方案

### 6.1 移除 JSON 写入 domain

修改 `metaweave/core/metadata/generator.py`：

1. 删除初始化阶段对 `configs/db_domains.yaml` 的反向索引加载
2. 删除 `_build_domain_reverse_index()`
3. 删除 `_process_table_from_ddl()` 中对 `table_profile.table_domains` 的赋值

修改 `metaweave/core/metadata/models.py`：

1. 删除 `TableProfile.table_domains` 字段
2. 删除 `TableProfile.to_dict()` 中输出 `table_domains`

预期结果：

1. `json` 与 `json_llm` 生成的 JSON 不再包含 domain
2. 修改 `db_domains.yaml` 后不需要重跑 `json/json_llm`

### 6.2 引入统一 DomainResolver

新增模块，例如：

- `metaweave/core/domains/resolver.py`

职责：

1. 读取 YAML
2. 构建双向映射
3. 处理表名标准化
4. 为 `rel_llm`、`cql`、未来 loader 提供统一接口

建议同时补充单元测试，覆盖：

1. 空 YAML
2. 大小写不敏感匹配
3. 单表多 domain
4. `_未分类_`
5. YAML 中表不存在于当前输入集合时的过滤行为

### 6.3 改造 rel_llm

修改 `metaweave/core/relationships/llm_relationship_discovery.py`：

1. 将 domain 解析职责从模块级函数中移出，避免继续依赖模块内部的 `_group_tables_by_domain()` 一类函数直接读取 JSON
2. 在 `LLMRelationshipDiscovery.__init__` 中注入 `DomainResolver` 实例，或至少注入显式 `domains_config_path`
3. 不建议把 `DomainResolver` 作为参数层层传给模块级函数；更推荐将表对生成能力收敛到 resolver 内部，由 `LLMRelationshipDiscovery` 直接调用
4. 不再依赖 JSON 中的 `table_profile.table_domains`
5. 改为基于 `DomainResolver` 直接对可用表集合做分组

新的分组逻辑应当是：

1. 先加载当前 `output/json` 中实际存在的表集合
2. 再根据 `db_domains.yaml` 中的表清单与当前可用表取交集
3. 基于交集结果生成 intra-domain / cross-domain 表对

这样即使 JSON 完全不带 `table_domains`，`rel_llm --domain` 仍然可以正常工作。

建议删除或弱化 `_validate_table_domains()`，因为该校验在新架构下已无意义。

推荐的调用方式如下：

1. CLI 层解析 `--domains-config`
2. CLI 层创建 `DomainResolver(domains_config_path=...)`
3. CLI 层将 resolver 注入 `LLMRelationshipDiscovery`
4. `LLMRelationshipDiscovery.discover()` 内部直接调用 `self.domain_resolver.resolve_table_pairs(...)`

不建议的方式如下：

1. 在 `DomainResolver` 内部自行推导默认路径
2. 在 `LLMRelationshipDiscovery` 内部再次硬编码 `configs/db_domains.yaml`
3. 继续保留“模块级函数 + 外部 YAML + JSON table_domains”三套并存逻辑

对现有模块级函数的处置建议如下：

1. `_group_tables_by_domain`
2. `generate_intra_domain_pairs`
3. `generate_cross_domain_pairs`
4. `get_table_pairs`

在 `DomainResolver.resolve_table_pairs()` 落地后，这些函数应删除，其能力统一由 resolver 替代。

若过渡期必须暂存，也只能保留为薄包装转发到 resolver，并明确标注为 deprecated；不建议长期保留两套表对生成逻辑。

### 6.4 改造 cql / cql_llm

修改 `metaweave/core/cql_generator/reader.py`：

1. 不再从 `table_profile.table_domains` 读 domain
2. 在构造 `TableNode` 时，通过 `DomainResolver` 动态查询当前表所属 domain

保留 `TableNode.table_domains` 字段是合理的，因为它属于 CQL 生成时的内部视图，而不是 Step 2 JSON schema。

修改 `metaweave/core/cql_generator/generator.py`：

1. 初始化 `JSONReader` 时增加 `domains_config_path` 或 `DomainResolver`
2. 统一使用 `configs/db_domains.yaml` 或 CLI 显式传入路径

修改 `metaweave/core/cql_generator/writer.py`：

1. 保持写入 `n.table_domains` 的能力
2. 但要重新审视空值覆盖策略

建议调整为：

1. 若本次生成得到非空 domain，则直接覆盖
2. 若本次生成得到空列表，也应允许显式覆盖为空

原因是：

1. domain 已转为运行时配置
2. 如果某表被从某个 domain 中移除，图节点也应同步清空或更新，而不是保留旧值

### 6.5 loader 侧策略

#### 6.5.1 table_schema_loader

当前无需改动。

若未来要在 schema embedding 中引入 domain，可直接：

1. 在 loader 初始化时加载 `DomainResolver`
2. 根据 `object_id` 或 `table_name` 反查 domain
3. 将 domain 作为额外 metadata 字段写入向量库

不建议通过 JSON 中间产物回传 domain。

#### 6.5.2 dim_value_loader

当前无需改动。

若未来要做 domain 级过滤或为向量记录打标签，也建议直接读 `db_domains.yaml`。

### 6.6 SQL 样例产物

`sql_rag` 当前已经直接读取 `db_domains.yaml`，无需跟随 JSON 改造。

若未来 `output/sql/*.json` 或其他最终业务样例中需要保留 domain，可继续保留，因为这些文件属于最终业务产物，而不是通用中间元数据。

## 7. 兼容策略

### 7.1 对旧 JSON 的兼容

在过渡期建议：

1. `rel_llm` 优先使用 `DomainResolver`
2. `cql/cql_llm` 优先使用 `DomainResolver`
3. 若旧 JSON 中仍含 `table_domains`，忽略它，不再作为主逻辑输入

这样可以避免新旧逻辑混用导致的歧义。

过渡期语义需要明确：

1. 阶段 2-3 中，JSON 中若仍存在 `table_domains`，它已经是废弃字段
2. 废弃字段仅为历史兼容残留，不再参与运行时逻辑
3. 直到阶段 4 删除写入逻辑前，允许该字段继续出现在旧产物中，但不得再作为功能依据

### 7.2 对测试的兼容

以下测试需要同步调整：

1. 与 `TableProfile.table_domains` 相关的单元测试
2. 与 `MetadataGenerator._build_domain_reverse_index()` 相关的测试
3. 与 `LLMRelationshipDiscovery._validate_table_domains()` 相关的测试
4. 与 CQL 读取 JSON 中 `table_domains` 的测试

建议新增新的测试分层：

1. `DomainResolver` 单元测试
2. `rel_llm --domain/--cross-domain` 过滤测试
3. `cql` 在 YAML 更新后无需重跑 JSON 的验证测试

## 8. 分阶段实施建议

### 阶段 1：引入单一来源能力

1. 新增 `DomainResolver`
2. 为其补充单元测试

### 阶段 2：改造 rel_llm

1. 将 `rel_llm` 的 domain 分组逻辑切换到 YAML
2. 移除对 JSON `table_domains` 的依赖
3. 验证 `--domain/--cross-domain` 行为
4. 明确标注 JSON 中若仍存在 `table_domains`，该字段已废弃，不再被读取

### 阶段 3：改造 cql/cql_llm

1. 在 CQL 生成时动态补 domain
2. 修正空值覆盖策略
3. 验证 YAML 修改后无需重跑 JSON
4. 明确标注 JSON 中若仍存在 `table_domains`，该字段已废弃，不再被读取

### 阶段 4：移除 JSON 注入逻辑

1. 删除 `MetadataGenerator` 中的 domain 反向索引逻辑
2. 删除 `TableProfile.table_domains`
3. 更新 JSON 相关测试与文档

建议按这个顺序推进，而不是一步到位删除。原因是：

1. 先把消费方改为直接读 YAML
2. 再删除 JSON 中的冗余字段
3. 风险更低，回归范围更容易控制

补充说明：

1. 阶段 4 的技术风险评估为低
2. 从实现依赖上看，阶段 2-3 完成后，`_build_domain_reverse_index` 的唯一剩余职责就是服务 `json` 步骤写入废弃字段
3. 因此阶段 4 可以与阶段 2-3 合并为同一个发布批次
4. 但工程动作顺序仍建议保持“先切消费方，再删写入方”，不要反向执行

## 9. 验收标准

完成后应满足以下验收条件：

1. `json/json_llm` 输出中不再包含 `table_domains`
2. 修改 `configs/db_domains.yaml` 后，不需要重跑 `json/json_llm`
3. `rel_llm --domain xxx` 能基于最新 YAML 生效
4. `rel_llm --cross-domain` 能基于最新 YAML 生效
5. `cql/cql_llm` 生成的表节点 domain 来自最新 YAML
6. 从某个 domain 中移除表后，重新生成 CQL 能正确反映该变化
7. `table_schema_loader` 与 `dim_value_loader` 主流程不受影响

## 10. 风险与注意事项

### 10.1 表名规范风险

`db_domains.yaml` 中使用的是 `database.schema.table`，而部分运行时对象可能只持有 `schema.table`。

需要统一规范：

1. YAML 映射使用 `database.schema.table`
2. 运行时若只有 `schema.table`，必须结合当前 database 名进行补全
3. 不允许每个调用方自行拼接三段式表名，应统一通过 `DomainResolver.normalize_table_name(...)` 处理

建议提供两类查询能力：

1. `get_domains_for_full_name("dvdrental.public.orders")`
2. `get_domains_for_schema_table("public.orders", db_name="dvdrental")`

这样可以避免重复出现类似 `f"{db}.{schema}.{table}".casefold()` 的分散拼接逻辑。

### 10.2 `_未分类_` 语义风险

`db_domains.yaml` 中 `_未分类_` 的 `tables: []` 是合法状态。

需要明确语义：

1. `DomainResolver` 仅表达“配置中显式声明的归属”
2. 对未命中的表返回 `[]`
3. 不自动补 `["_未分类_"]`
4. 是否把“未命中表”视作未分类，由 `rel_llm`、`sql_rag`、报表展示层等上层逻辑自行决定

### 10.3 YAML 与实际产物集合不一致

YAML 里可能存在当前 JSON/MD 中不存在的表。

建议策略：

1. 只对当前实际可用表集合做交集过滤
2. 不因 YAML 中存在额外表而报错
3. 仅记录 warning

### 10.4 旧图数据残留

如果 CQL writer 继续沿用“空值不覆盖”的策略，则 domain 删除无法生效。

因此本次改造必须同时审视 writer 的覆盖行为。

## 11. 结论

本方案建议将 `domain` 从 Step 2 JSON 中间产物中移出，恢复为 `configs/db_domains.yaml` 的单一事实来源。  
这能显著降低 `db_domains.yaml` 调整后的重跑成本，消除 YAML 与 JSON 双份事实来源的不一致问题，并使 `rel_llm`、`cql` 等后续阶段能够始终基于最新 domain 配置运行。

从当前代码现状看，这一改造既符合职责边界，也能修复现有“代码依赖 JSON domain、但实际 JSON 未稳定产出该字段”的隐性问题，建议实施。
