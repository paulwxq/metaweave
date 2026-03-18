# 61_dim_value 多列合并 Embedding 改造方案

## 1. 需求背景

### 1.1 现状

`dim_value_loader` 当前支持在 `dim_tables.yaml` 中为每张维表指定 `embedding_col`，支持单列和多列两种格式：

```yaml
public.dim_store:
  embedding_col: store_name               # 单列
public.dim_product:
  embedding_col: [product_name, category] # 多列（逐列独立处理）
```

多列配置下，每一列被**独立向量化**，每列产生各自的 embedding 记录，写入 `dim_value_embeddings` 时 `col_name` 和 `col_value` 均为单列的值。

### 1.2 问题

在实际业务中，某些维度值的语义需要**多个字段组合才能完整表达**。例如：

- 门店名称 `store_name = "万达广场"` + 地址 `address = "北京朝阳区建国路93号"` 组合后，向量检索精度更高
- 品牌 `brand` 是独立维度，需要单独向量化

当前架构无法在同一张表中混合使用"合并列"和"独立列"两种策略。

### 1.3 改造目标

- 支持将多列合并为**一个 embedding** 写入向量库
- 支持在同一张表中混合配置"合并列组"和"独立列"
- `col_name` 与 `col_value` 使用**同一分隔符**拼接，保持一致性
- 分隔符可在 loader 配置中设定全局默认值，在 `dim_tables.yaml` 中按表覆盖
- 默认分隔符为竖线 `|`
- 向后兼容现有配置格式（无需修改已有 yaml 文件）

---

## 2. 配置设计

### 2.1 新增配置格式

`dim_tables.yaml` 的 `embedding_col` 字段在现有三种格式基础上，新增**嵌套列表（合并组）**支持：

```yaml
# 格式说明：
#
# 现有格式（保持兼容）：
#   embedding_col: column_name                    # 单列独立
#   embedding_col: [col1, col2]                   # 多列，逐列独立（每列单独embedding）
#   embedding_col: col1, col2                     # 逗号字符串，逐列独立（自动拆分）
#
# 新增格式：
#   embedding_col:                                # 混合模式
#     - [col1, col2]                              # 列表元素为列表 → 合并为一个embedding
#     - col3                                      # 列表元素为字符串 → 独立embedding

databases:
  highway_db:
    tables:
      public.dim_store:
        merge_separator: "|"       # 可选，覆盖全局默认值
        embedding_col:
          - [store_name, address]  # 合并组：store_name|address → 万达广场|北京朝阳区
          - brand                  # 独立列：brand → 耐克

      public.dim_product:
        embedding_col:
          - [product_name, category, spec]   # 三列合并
          - sku_code                         # 独立列

      public.dim_region:
        embedding_col: region_name           # 旧格式，保持兼容
```

### 2.2 格式解析规则

| 配置值类型 | 示例 | 解析结果 |
|---|---|---|
| `null` | `embedding_col: null` | 空列表，跳过该表 |
| 字符串（无逗号） | `embedding_col: region_name` | `[独立列(region_name)]` |
| 字符串（含逗号） | `embedding_col: col1, col2` | `[独立列(col1), 独立列(col2)]` |
| YAML 列表（元素均为字符串） | `embedding_col: [col1, col2]` | `[独立列(col1), 独立列(col2)]` |
| YAML 列表（元素含子列表） | `embedding_col:` `- [col1, col2]` `- col3` | `[合并组(col1,col2), 独立列(col3)]` |

> **向后兼容保证**：前三种格式行为与现有代码完全一致，无需修改已有 yaml 配置。

### 2.3 全局分隔符配置

在 `metadata_config.yaml` 的 `dim_loader` 段新增 `merge_separator` 字段：

```yaml
dim_loader:
  collection_name: dim_value_embeddings
  config_file: configs/dim_tables.yaml
  merge_separator: "|"           # 新增：合并列分隔符，默认竖线
  options:
    batch_size: 100
    max_records_per_table: 0
    skip_empty_values: true
    truncate_long_text: true
    max_text_length: 1024
```

### 2.4 分隔符优先级

```
dim_tables.yaml 表级 merge_separator
    > metadata_config.yaml dim_loader.merge_separator
    > 内置默认值 "|"
```

---

## 3. 数据模型变更

### 3.1 dim_value_embeddings Collection（无结构变更）

`dim_value_embeddings` 的 Schema **不需要修改**，字段含义扩展如下：

| 字段 | 类型 | 单列时 | 合并列时 |
|---|---|---|---|
| `table_name` | VARCHAR(128) | `db.schema.table` | 同左，无变化 |
| `col_name` | VARCHAR(128) | `store_name` | `store_name\|address`（分隔符拼接列名） |
| `col_value` | VARCHAR(1024) | `万达广场` | `万达广场\|北京朝阳区建国路93号`（分隔符拼接值） |
| `embedding` | FLOAT_VECTOR(1024) | 单列值的向量 | 拼接后文本的向量 |
| `update_ts` | INT64 | Unix 秒 | 同左，无变化 |

**`col_name` 长度约束提示**：VARCHAR(128) 在合并多个长列名时存在截断风险。改造中需在写入前做截断保护，并在文档中注明合并列数建议不超过 4 个。

### 3.2 写入示例

配置：`embedding_col: - [store_name, address]`，分隔符 `|`，表有 2 条记录：

| `col_name` | `col_value` | `embedding` |
|---|---|---|
| `store_name\|address` | `万达广场\|北京朝阳区建国路93号` | vector(...) |
| `store_name\|address` | `国贸商城\|北京朝阳区建国门外大街1号` | vector(...) |

配置：`embedding_col: - brand`，独立列：

| `col_name` | `col_value` | `embedding` |
|---|---|---|
| `brand` | `耐克` | vector(...) |
| `brand` | `阿迪达斯` | vector(...) |

---

## 4. 代码改造设计

### 4.1 涉及文件清单

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `metaweave/core/dim_value/models.py` | 修改 | 新增 `EmbeddingGroup` 类型；`DimTableConfig` 增加 `merge_separator` 字段；`embedding_cols_list` 升级为 `embedding_groups` |
| `metaweave/core/loaders/dim_value_loader.py` | 修改 | `load()` 循环改为按 group 处理；`_load_table` 支持多列合并查询；`_fetch_table_data` 支持多列 SQL |
| `configs/dim_tables.yaml` | 修改 | 更新注释说明，新增合并格式示例 |
| `configs/metadata_config.yaml` | 修改 | `dim_loader` 段新增 `merge_separator: "\|"` |
| `tests/unit/metaweave/dim_value/test_dim_value_loader.py` | 修改 | 补充合并列测试用例 |

### 4.2 models.py 改造

**新增 `EmbeddingGroup` 数据类**，表示一个 embedding 处理单元（可以是单列或合并列组）：

```python
@dataclass
class EmbeddingGroup:
    """一个 embedding 处理单元。
    
    - 单列：columns = ["store_name"]，is_merged = False
    - 合并组：columns = ["store_name", "address"]，is_merged = True
    """
    columns: List[str]
    separator: str = "|"

    @property
    def is_merged(self) -> bool:
        return len(self.columns) > 1

    @property
    def col_name(self) -> str:
        """写入 Milvus col_name 字段的值。"""
        return self.separator.join(self.columns)
```

**`DimTableConfig` 新增字段**：

```python
@dataclass
class DimTableConfig:
    schema: str
    table: str
    embedding_col: Union[str, List[Any], None]
    merge_separator: str = "|"        # 新增：来自表级配置或全局默认值

    @property
    def embedding_groups(self) -> List[EmbeddingGroup]:
        """返回 EmbeddingGroup 列表，统一处理所有格式。"""
        ...
```

**`embedding_groups` 解析逻辑**（替代现有 `embedding_cols_list`）：

```
输入 embedding_col 值：
  → None           → []
  → 字符串（无逗号） → [EmbeddingGroup(["col"])]
  → 字符串（有逗号） → [EmbeddingGroup(["col1"]), EmbeddingGroup(["col2"])]
  → List[str]      → [EmbeddingGroup(["col1"]), EmbeddingGroup(["col2"])]（逐元素，向后兼容）
  → List[Any]（含子列表） → 按元素类型：
       str  → EmbeddingGroup([str])        独立列
       list → EmbeddingGroup(list)         合并组
```

> `embedding_cols_list` 属性保留，内部委托给 `embedding_groups`，避免破坏其他潜在引用。

### 4.3 dim_value_loader.py 改造

**`load()` 循环改造**（当前按列名迭代，改为按 group 迭代）：

```python
# 改造前
for col_idx, embedding_col in enumerate(embedding_cols, 1):
    table_stats = self._load_table(schema, table, embedding_col)

# 改造后
separator = dim_cfg.merge_separator  # 表级或全局分隔符
for grp_idx, group in enumerate(dim_cfg.embedding_groups, 1):
    table_stats = self._load_table(schema, table, group, separator)
```

**`_fetch_table_data` 改造**：

- 单列（`group.is_merged == False`）：行为与现有完全一致
- 合并列（`group.is_merged == True`）：SQL 使用 `CONCAT_WS` 拼接多列

```sql
-- 合并列 SQL（separator = '|'，columns = ['store_name', 'address']）
SELECT DISTINCT
    CONCAT_WS('|', store_name, address) AS col_value
FROM public.dim_store
WHERE store_name IS NOT NULL
  AND address IS NOT NULL
  AND LENGTH(BTRIM(CONCAT_WS('|', store_name, address))) > 0
```

> 使用 `CONCAT_WS`（带分隔符连接）而非手动拼接，PostgreSQL 原生支持，会自动忽略 NULL 值。

**`_load_table` 改造**：写入 Milvus 时，`col_name` 使用 `group.col_name`（分隔符拼接的列名组合）。

### 4.4 LoaderOptions 改造

`LoaderOptions` 增加 `merge_separator` 字段：

```python
@dataclass
class LoaderOptions:
    batch_size: int = 100
    max_records_per_table: int = 0
    skip_empty_values: bool = True
    truncate_long_text: bool = True
    max_text_length: int = 1024
    merge_separator: str = "|"        # 新增
```

从 `dim_loader` 配置段读取并向下传递给各 `DimTableConfig`。

---

## 5. 向后兼容性保证

| 场景 | 现有配置 | 改造后行为 | 兼容？ |
|---|---|---|---|
| 单列字符串 | `embedding_col: region_name` | 解析为 `[EmbeddingGroup(["region_name"])]` | ✅ |
| 多列字符串 | `embedding_col: col1, col2` | 解析为 `[EmbeddingGroup(["col1"]), EmbeddingGroup(["col2"])]` | ✅ |
| 多列列表 | `embedding_col: [col1, col2]` | 解析为 `[EmbeddingGroup(["col1"]), EmbeddingGroup(["col2"])]` | ✅ |
| null | `embedding_col: null` | 解析为 `[]`，跳过 | ✅ |
| 全局配置无 `merge_separator` | 未配置 | 使用内置默认值 `"\|"` | ✅ |

---

## 6. 测试用例设计

### 6.1 单元测试（models.py）

| 测试用例 | 输入 | 期望输出 |
|---|---|---|
| 单列字符串 | `embedding_col: "name"` | `[EmbeddingGroup(["name"])]` |
| 逗号分隔字符串 | `embedding_col: "col1, col2"` | 2 个独立 Group |
| YAML 列表（字符串元素） | `[col1, col2]` | 2 个独立 Group（兼容旧格式） |
| YAML 嵌套列表 | `[[col1, col2], col3]` | 1 个合并 Group + 1 个独立 Group |
| null | `null` | 空列表 |
| `col_name` 拼接（`\|`） | `EmbeddingGroup(["store_name","address"], "\|")` | `col_name = "store_name\|address"` |

### 6.2 集成测试（dim_value_loader.py）

| 测试用例 | 说明 |
|---|---|
| 合并列 SQL 拼接正确 | 验证 `_fetch_table_data` 生成的 SQL 含 `CONCAT_WS` |
| 合并列 `col_name` 写入正确 | 验证 Milvus 记录的 `col_name` 为分隔符拼接 |
| 合并列 `col_value` 写入正确 | 验证 `col_value` 为多列值的分隔符拼接 |
| 分隔符优先级 | 表级 > 全局 > 默认值 |
| 向后兼容：旧格式不受影响 | 旧配置格式处理结果与改造前一致 |

---

## 7. 实施计划

| 步骤 | 内容 | 文件 |
|---|---|---|
| 1 | 升级数据模型，新增 `EmbeddingGroup`，改造 `DimTableConfig` | `models.py` |
| 2 | 改造 loader，支持按 group 处理，合并列 SQL 生成 | `dim_value_loader.py` |
| 3 | 更新 `dim_tables.yaml` 注释和示例 | `configs/dim_tables.yaml` |
| 4 | 更新 `metadata_config.yaml` 新增 `merge_separator` 配置项 | `configs/metadata_config.yaml` |
| 5 | 补充单元测试和集成测试 | `tests/unit/...` |

---

## 8. 设计决策记录

以下事项已与业务方确认，作为设计基准：

| # | 事项 | 决策 |
|---|---|---|
| 1 | **NULL 值处理** | 合并组中**至少一列有值**即保留，全部为 NULL 才跳过行。直接使用 `CONCAT_WS`，其天然忽略 NULL 列的行为符合预期，无需额外过滤逻辑 |
| 2 | **`col_name` 长度限制** | 暂不处理。`dim_value_embeddings` 表将在下一阶段重建并扩充 `col_name` 字段长度，本次改造不加截断保护 |
| 3 | **历史数据迁移** | 不需要迁移。系统尚未上线，无存量数据，改造后直接全量重建即可 |

---

## 9. 状态

- [x] 需求讨论完成
- [x] 设计决策确认
- [ ] 待审批后开始编码
