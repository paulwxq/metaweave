# 2. Milvus 与 pgvector 评估及存储选型建议

日期：2026-09-10  
状态：可行性评估与讨论建议，尚未实施存储改造。

## 1. 结论

**建议近期保留 Milvus，使用 PostgreSQL 保存业务与作业状态，使用 Neo4j 保存图关系，暂不启用 pgvector。**

当前 MetaWeave 使用的 Milvus 功能可以通过 PostgreSQL + pgvector 实现，未发现必须依赖 Milvus 的业务功能。但功能可替换不代表迁移就是当前最有价值的选择。

结合讨论中的实际条件：

- 当前 Milvus 实现已经运行可用。
- 未来可能增加多向量检索、结果融合或其他索引算法。
- 用户关注规模增长后的扩展能力，希望避免迁移后再迁回。
- 后续还有框架升级、Docker 部署、关系发现质量优化及 REST API 作业管理需要完成。

因此，应优先完成服务化和作业可靠性改造，将存储接口适度隔离，暂时只维护 Milvus 一个向量后端。该结论属于选型建议，不代表其他改造方案已经确定。

## 2. 当前 Milvus 使用范围

本次检查覆盖三个向量加载器、公共 Milvus 客户端、检索测试、配置及现有 pgvector 预留代码。没有连接数据库执行性能测试，下游 NL2SQL 的完整检索逻辑不在本次检查范围内。

### 2.1 三类向量数据

| 数据 | 向量化内容 | 附带信息 | 写入方式 |
|---|---|---|---|
| 表和字段结构 | 表、字段描述 | 对象 ID、对象类型、所属表、时间字段提示、表分类 | 全量 insert，增量 upsert |
| 维度值 | 部门名称、产品类别等文本值 | 表名、列名、原始值、更新时间 | 自动 ID，insert |
| SQL 样例 | 问题文本 | Question-SQL JSON 字符串、业务域、更新时间 | 内容哈希 ID，upsert |

三个加载器均采用单个稠密向量字段、HNSW 索引及 COSINE 度量，构建参数为 `M=16`、`efConstruction=200`。

当前配置为 1024 维。维度值加载器直接固定为 1024 维，其他两个加载器从配置获取维度。

代码依据：

- [表结构加载器](../../metaweave/core/loaders/table_schema_loader.py)
- [维度值加载器](../../metaweave/core/loaders/dim_value_loader.py)
- [SQL 样例加载器](../../metaweave/core/sql_rag/loader.py)
- [公共 Milvus 客户端](../../services/vector_db/milvus_client.py)

### 2.2 当前检索能力

仓库中明确出现的向量检索流程为：

```text
查询文本 → Embedding → 可选表名过滤 → Top-K → 返回原始值与相似度
```

参见 [维度值检索测试](../../tests/test_dim_value_search.py)。

未发现当前业务代码使用稀疏向量、BM25、多向量混合检索、服务端重排序、分组搜索或业务级分区路由。客户端设置了集合创建参数 `shards_num`，但业务代码没有直接操作分片。

## 3. pgvector 替换的可行性与边界

| 当前用法 | PostgreSQL + pgvector 对应方式 |
|---|---|
| Collection 与固定字段 Schema | 数据表与列定义 |
| FLOAT_VECTOR(1024) | vector(1024) |
| HNSW + COSINE | HNSW + vector_cosine_ops |
| Top-K 检索 | 距离排序 + LIMIT |
| 标量过滤与字段投影 | 参数化 WHERE 与 SELECT |
| 自动主键 | identity 列 |
| insert / upsert | INSERT / ON CONFLICT DO UPDATE |
| 集合清空重建 | 对应目标表的数据清理或重建 |
| load / flush | 通过 PostgreSQL 缓冲管理和事务机制承担相应职责，不照搬接口语义 |

pgvector 提供当前所需的向量与近邻检索能力，PostgreSQL 提供关系数据和写入冲突处理能力。参见 [pgvector 官方文档](https://github.com/pgvector/pgvector) 和 [PostgreSQL INSERT 文档](https://www.postgresql.org/docs/current/sql-insert.html)。

### 3.1 相似度分数

Milvus COSINE 检索返回的分数越大越相似；pgvector 的 `<=>` 返回余弦距离，越小越相似。迁移时应统一对外返回：

```text
similarity = 1 - cosine_distance
```

余弦相似度理论范围为 `[-1, 1]`，不能把它当作固定的 `[0, 1]`。下游排序和阈值过滤必须同步核对。参见 [Milvus 度量说明](https://milvus.io/docs/metric.md)。

### 3.2 过滤与召回

pgvector 使用近似索引时，过滤可能在索引扫描之后执行，导致符合条件的结果不足。可评估迭代扫描、增加搜索范围、部分索引、分区，或对较小过滤结果集进行精确排序。迭代扫描自 pgvector 0.8.0 起提供，仍受扫描上限约束。

这意味着将 Milvus `expr` 改写成 SQL `WHERE` 后，还需要验证查询计划、召回率与延迟。

### 3.3 维度与模型一致性

当前 1024 维可使用 pgvector 普通 `vector` HNSW 索引。讨论时官方文档列出的该索引类型上限为 2000 维，更高维模型需另行评估表示方式。

迁移比较应使用同一模型、同一维度和同一批向量，避免把 Embedding 变化误判为数据库差异。

### 3.4 更新语义

- 维度值目前采用自动 ID 与追加写入；改为业务唯一键去重属于独立行为变更。
- upsert 不会自动删除已失效记录，应明确全量刷新、按源库刷新和增量更新的范围。
- 相同 HNSW 参数不保证两个系统具有相同速度、内存消耗或召回结果。

过滤、维度与索引依据见 [pgvector 官方文档](https://github.com/pgvector/pgvector)。

## 4. 多向量字段与算法能力的区别

### 4.1 两者都支持多个向量字段

pgvector 没有“一张表只能有一个向量字段”的限制。例如：

```sql
CREATE TABLE table_metadata (
    id bigint PRIMARY KEY,
    name_embedding vector(1024),
    description_embedding vector(1024)
);

CREATE INDEX ON table_metadata
USING hnsw (name_embedding vector_cosine_ops);

CREATE INDEX ON table_metadata
USING hnsw (description_embedding vector_cosine_ops);
```

一条 SQL 也可以通过子查询或 CTE 对多个向量字段分别召回并融合结果。区别在于是否有现成的多路检索接口。

| 能力 | PostgreSQL + pgvector | Milvus |
|---|---|---|
| 同一记录保存多个向量 | 支持 | 支持 |
| 各向量字段分别建索引 | 支持 | 支持 |
| 一个请求组织多路召回 | 可通过 SQL 组织 | 提供 hybrid_search |
| 融合与重排序 | 自行编写 SQL 或应用逻辑 | 提供加权、RRF 等方式 |

直接按多个向量距离的加权和排序，通常不能直接利用两个独立 HNSW 索引加速综合排序。常见做法是各路分别取候选，再融合；候选截断会影响最终召回。

Milvus 对这类流程的封装更完整。参见 [多向量混合检索官方文档](https://milvus.io/docs/multi-vector-search.md)。

### 4.2 Milvus 提供更多索引选择

pgvector 本体的近似索引主要为 HNSW 与 IVFFlat。Milvus 还提供 IVF_PQ、IVF_SQ8、SCANN、DiskANN 及部分 GPU 索引等选择，具体可用性取决于版本、向量类型和部署条件。

pgvector 也有半精度、二进制量化等优化手段，但不能视为拥有上述同名索引实现。参见 [Milvus 索引说明](https://milvus.io/docs/index-explained.md)。

COSINE、L2、内积属于距离度量；HNSW、IVF、DiskANN 属于索引或搜索算法，选型时应区分。

当前 MetaWeave 没有使用这些额外能力。如果未来引入“字段名向量 + 中文含义向量 + 样例内容向量”的多路检索，Milvus 的现成接口会更有价值。

## 5. 当前 pgvector 代码不能直接启用

仓库已有 pgvector Python 依赖、连接池中的向量类型注册及旧 SQL 建表脚本，但后端实现尚不完整：

- [PgVectorClient](../../metaweave/services/vector_db/pgvector_client.py) 的主要方法仍抛出 `NotImplementedError`。
- 表结构和维度值加载器明确拒绝非 Milvus 后端。
- SQL 样例加载器直接读取 Milvus 配置。
- 三个加载器直接构造 `pymilvus.FieldSchema`。
- 当前公共接口未完整覆盖 upsert 与 search，Milvus 公共客户端也未继承该基类。
- [旧 pgvector.sql](../../services/db/migrations/pgvector.sql) 与当前产物字段不一致，其中维度值表没有向量列，不能直接作为迁移脚本。

因此，配置中存在 `pgvector` 选项不等于已实现后端切换。

## 6. 推荐的存储职责划分

| 组件 | 推荐职责 | 当前与规划的区别 |
|---|---|---|
| PostgreSQL | 作业参数、状态、进度、错误、数据源配置、元数据版本、产物位置；下游对话历史等 | 作业与对话相关表属于规划，当前仓库未体现完整实现 |
| Milvus | 表结构、维度值、SQL 样例的向量存储和检索 | 当前已实现 |
| Neo4j | 表、字段及其关联关系，供下游图查询 | 当前已实现生成与加载 |
| pgvector | 暂不启用 | 不必与 Milvus 同时维护 |

pgvector 是 PostgreSQL 的可选扩展。保留 Milvus 不意味着必须同时启用 pgvector，最终服务组合可以是 **Milvus + PostgreSQL + Neo4j**。

用户提及的对话历史可能属于下游 NL2SQL 系统，当前 MetaWeave 仓库未体现该存储实现。即便不计对话历史，REST API 作业管理也会为 PostgreSQL 带来明确职责。

建议 PostgreSQL 中的控制数据与被分析的业务数据库明确分离。是否使用独立实例，应结合资源、权限和运维条件决定。

## 7. 横向扩展的判断

不宜将选型建立在“pgvector 完全无法横向扩展”的绝对表述上。

pgvector 本体不提供与 Milvus 同形态的分布式向量服务架构。PostgreSQL 的读副本可以分担读取，但不会自动把一个写入数据集分片；表分区也不等于跨机器分布式存储。若借助额外分布式方案，需要进一步设计跨分片召回、结果合并和全局 Top-K。

Milvus 的分布式架构更贴近专门的向量服务，但选择 Milvus 也不等于自动获得无限扩展能力；实际容量与延迟仍受部署模式、索引、硬件和查询负载影响。参见 [Milvus 架构说明](https://milvus.io/docs/architecture_overview.md)。

当前保留 Milvus 的主要理由是已有实现可用、未来能力方向匹配，以及避免往返迁移成本，而不是尚未测量的“大规模”假设。

## 8. 近期实施建议

### 8.1 保留现有向量后端

先完成框架升级、关系发现质量优化、Docker 部署与 REST API 作业管理。暂不实现完整 pgvector 后端，不进行双写。

### 8.2 适度隔离存储接口

将业务代码对 `pymilvus`、Schema、过滤表达式和返回对象的直接依赖集中到适配层。接口按业务需要覆盖初始化、批量写入、upsert、过滤检索、范围删除和统计即可。

当前仅维护 Milvus 实现，避免为尚未使用的后端构建复杂抽象。

### 8.3 保持数据归属与可重建性

PostgreSQL 保存业务及作业状态，Milvus 保存向量检索数据，Neo4j 保存图关系。向量和图数据尽量由版本化元数据产物重建，并记录模型、维度及生成版本，避免无法判断数据来源。

后续并发作业设计还应明确源库、项目或租户的数据隔离，以及清理和更新范围。

### 8.4 根据实际负载扩容

持续关注向量数量、查询 P95、并发、过滤召回率、批量写入耗时、索引构建时间及内存和磁盘占用。

当前元数据向量规模由表、字段和 SQL 样例数量决定；维度值可能成为主要数据量来源。在线查询压力还需结合下游 NL2SQL 使用情况评估。

如果以后重新评估 pgvector，应使用相同向量与固定查询集，对照精确检索评估 Recall@K，并覆盖强过滤、重复写入、增量更新和全量刷新。不能只比较两个近似索引的 Top-K 是否逐条一致。

## 9. 后续讨论范围

本次不修改代码或部署配置。下一步可继续讨论 Docker 服务划分和初始化方式；完整的资源规格、扩容架构及性能结论，需要实际数据规模和负载测试支持。
