# rel vs rel_llm 命令对比与 JSON 兼容性评估

> **文档版本**: 1.1  
> **创建日期**: 2025-12-26  
> **更新日期**: 2025-12-26  
> **评估范围**: `metaweave metadata --step rel` vs `metaweave metadata --step rel_llm`

---

## 📋 目录

- [执行摘要](#执行摘要)
- [命令功能对比](#命令功能对比)
- [JSON Schema 兼容性验证](#json-schema-兼容性验证)
- [关键问题与解决方案](#关键问题与解决方案)
- [输出目录与格式对比](#输出目录与格式对比)
- [字段依赖详细分析](#字段依赖详细分析)
- [运行建议](#运行建议)

---

## 执行摘要

### ✅ 核心结论

1. **JSON Schema 兼容性（输入）**: ✅ **完全兼容** - 当前 `output/json` 目录下的 JSON 文件在字段结构上 100% 兼容两个命令
2. **数据完整性**: ✅ **所有必需字段存在** - 包含基础元数据、LLM 增强内容、样例数据
3. **关键问题 1**: ❌ **输入目录配置错误** - `rel_llm` 步骤硬编码读取废弃的 `json_llm_directory` 配置
4. **关键问题 2**: ⚠️ **输出目录相同** - 两个命令输出到相同文件，会相互覆盖
5. **关键问题 3**: ❌ **输出格式不同** - JSON 结构差异可能导致下游工具不兼容
6. **修复优先级**: 🔴 **高** - 必须修复输入目录配置读取逻辑；建议分离输出目录或统一格式

### 🎯 评估结果速览

| 评估维度 | 结论 | 信心度 | 备注 |
|---------|------|--------|------|
| **JSON Schema 兼容性（输入）** | ✅ 完全兼容 | 100% | 所有字段存在且格式正确 |
| **输出目录配置** | ⚠️ 相同目录 | 100% | 会相互覆盖文件 |
| **输出格式兼容性** | ❌ 格式不同 | - | 统计字段和元数据有差异 |
| **`rel` 步骤可用性** | ✅ 可正常运行 | 100% | 正确读取 `output/json` 目录 |
| **`rel_llm` 步骤可用性** | ❌ 需要修复 | - | 错误读取 `json_llm_directory` |
| **必需字段完整性** | ✅ 所有字段存在 | 100% | 包括外键、逻辑主键、样例数据 |
| **外键格式正确性** | ✅ 格式标准 | 100% | 单列和复合外键都支持 |
| **样例数据可用性** | ✅ 数据完整 | 100% | LLM 关系推断的关键输入 |

---

## 命令功能对比

### 核心功能差异

两个命令的主要差异在于**关系发现方法**和**数据源**：

| 对比维度 | `--step rel` | `--step rel_llm` |
|---------|-------------|------------------|
| **关系发现方法** | 规则-based 算法 | LLM 辅助推理 |
| **核心技术** | 6 维度评分体系 | 大语言模型语义理解 |
| **数据源** | `output/json` 目录 | `output/json_llm` 目录（配置问题） |
| **输入依赖** | 基础元数据 + 数据库查询 | 完整 JSON + 样例数据 |
| **外部依赖** | 仅需数据库连接 | 需要 LLM API Key |
| **执行时间** | 较快（几分钟） | 较慢（可能几十分钟） |
| **并发处理** | 数据库并发查询 | LLM API 批量调用 |
| **资源消耗** | 较低 | 较高（API 调用费用） |

### 技术实现对比

#### `--step rel` 技术栈

```python
# 使用 RelationshipDiscoveryPipeline 类
pipeline = RelationshipDiscoveryPipeline(config_path)
result = pipeline.discover()
```

**处理流程**：
1. 加载 JSON 元数据和外键约束
2. 生成候选关系对（复合键 + 单列）
3. 多维度评分：
   - inclusion_rate (55%): 数据包含率
   - name_similarity (20%): 列名相似度
   - type_compatibility (15%): 类型兼容性
   - jaccard_index (10%): Jaccard 相似度
4. 决策过滤和关系抑制
5. 输出 JSON + Markdown

**优势**：
- ✅ 基于统计数据的精确评分
- ✅ 适合处理大量表的高效算法
- ✅ 稳定的规则-based 推理结果
- ✅ 无外部依赖，适合离线环境

#### `--step rel_llm` 技术栈

```python
# 使用 LLMRelationshipDiscovery 类
discovery = LLMRelationshipDiscovery(config, connector)
result = discovery.discover()
```

**处理流程**：
1. 加载 LLM 增强的 JSON 元数据
2. 两两组合表对，构建 LLM 提示词：
   ```python
   prompt = RELATIONSHIP_DISCOVERY_PROMPT.format(
       table1_name=table1_name,
       table1_json=json.dumps(table1, ensure_ascii=False, indent=2),
       table2_name=table2_name,
       table2_json=json.dumps(table2, ensure_ascii=False, indent=2),
   )
   ```
3. LLM 分析并返回候选关系（单列或复合键）
4. 复用 `RelationshipScorer` 进行评分验证
5. 决策过滤和输出

**优势**：
- ✅ 能发现语义关联（通过注释理解业务关系）
- ✅ 支持复合键的复杂关系推断
- ✅ 可能发现传统算法遗漏的关系模式
- ✅ 适合处理复杂业务逻辑

### 适用场景对比

| 场景 | 推荐命令 | 理由 |
|------|---------|------|
| **快速原型/开发环境** | `rel` | 无需外部依赖，执行迅速 |
| **生产环境/高质量需求** | `rel_llm` | LLM 语义理解更准确 |
| **资源受限环境** | `rel` | 更高效稳定，无 API 费用 |
| **CI/CD 流水线** | `rel` | 稳定、无外部依赖 |
| **复杂业务逻辑** | `rel_llm` | LLM 能理解语义关联 |
| **离线环境** | `rel` | 不需要网络连接 |

---

## JSON Schema 兼容性验证

### ✅ 完全兼容确认

当前 `output/json` 目录下的 JSON 文件**同时包含了两个命令所需的所有字段**，实现了完美的向后兼容和功能增强：

```json
{
  "metadata_version": "2.0",
  "generated_at": "2025-12-26T05:34:41.519200Z",
  "llm_enhanced_at": "2025-12-26T05:34:54.050816+00:00",  // ✅ LLM 增强标记
  
  "table_info": { /* 基础表信息 */ },                      // ✅ 两者都需要
  "column_profiles": {                                     // ✅ 两者都需要
    "column_name": {
      "statistics": { /* ... */ },                         // ✅ rel 用于评分
      "semantic_analysis": { /* ... */ },                  // ✅ 保留但不影响兼容性
      "structure_flags": { /* ... */ },                    // ✅ rel 用于候选生成
      "role_specific_info": { /* ... */ }                  // ✅ 保留但不影响兼容性
    }
  },
  "table_profile": {
    "physical_constraints": {                              // ✅ 两者都需要
      "foreign_keys": [ /* ... */ ],                       // ✅ 外键直通
      "unique_constraints": [ /* ... */ ]                  // ✅ 候选生成
    },
    "logical_keys": {                                      // ✅ rel 需要
      "candidate_primary_keys": [ /* ... */ ]
    }
  },
  "sample_records": {                                      // ✅ rel_llm 关键字段
    "records": [ /* ... */ ]                               // ✅ LLM 推理的数据基础
  }
}
```

### 字段完整性验证

所有必需字段都已通过验证：

| 字段路径 | `rel` | `rel_llm` | 当前状态 | 数据示例 |
|---------|-------|-----------|----------|---------|
| `table_info.schema_name` | ✅ | ✅ | ✅ | `"public"` |
| `table_info.table_name` | ✅ | ✅ | ✅ | `"dim_company"` |
| `table_info.comment` | ⚪ | ✅ | ✅ | `"公司维表"` |
| `column_profiles.<col>.data_type` | ✅ | ✅ | ✅ | `"integer"` |
| `column_profiles.<col>.statistics` | ✅ | ✅ | ✅ | `{unique_count, null_rate...}` |
| `column_profiles.<col>.semantic_analysis` | ⚪ | ⚪ | ✅ | `{semantic_role...}` |
| `column_profiles.<col>.structure_flags` | ✅ | ⚪ | ✅ | `{is_primary_key...}` |
| `table_profile.physical_constraints` | ✅ | ✅ | ✅ | `{primary_key, foreign_keys...}` |
| `table_profile.logical_keys` | ✅ | ⚪ | ✅ | `{candidate_primary_keys...}` |
| `sample_records.records` | ⚪ | ✅ | ✅ | `[{col: val...}]` |

**图例**：
- ✅ 必需字段
- ⚪ 可选字段（代码使用 `.get()` 安全访问）

### 外键格式验证

从实际 JSON 文件验证外键格式：

```json
// ✅ 单列外键（public.employee.json）
"foreign_keys": [
  {
    "constraint_name": "fk_employee_department",
    "source_columns": ["dept_id"],
    "target_schema": "public",
    "target_table": "department",
    "target_columns": ["dept_id"],
    "on_delete": "NO ACTION",
    "on_update": "NO ACTION"
  }
]

// ✅ 复合外键（public.order_item.json）
"foreign_keys": [
  {
    "constraint_name": "fk_order_item_header",
    "source_columns": ["order_date", "order_id"],
    "target_schema": "public",
    "target_table": "order_header",
    "target_columns": ["order_date", "order_id"],
    "on_delete": "NO ACTION",
    "on_update": "NO ACTION"
  }
]
```

**验证结果**: ✅ 外键格式与 `MetadataRepository.collect_foreign_keys()` 代码要求完全匹配。

### 样例数据验证

从 `public.dim_store.json` 验证样例数据：

```json
"sample_records": {
  "sample_method": "random",
  "sample_size": 5,
  "total_rows": 9,
  "sampled_at": "2025-12-24T04:52:54.300740Z",
  "records": [
    {
      "store_id": 101,
      "store_name": "京东便利天河岗顶店",
      "company_id": 1,
      "region_id": 440106
    },
    {
      "store_id": 103,
      "store_name": "京东便利南京新街口店",
      "company_id": 1,
      "region_id": 320106
    }
    // ... 更多记录
  ]
}
```

**验证结果**: ✅ 样例数据完整，LLM 可以基于这些实际数据进行关系推断。

---

## 关键问题与解决方案

### ❌ 问题：目录配置不一致

#### 问题描述

| 命令 | 代码读取的配置键 | 默认目录 | 实际情况 |
|------|-----------------|---------|---------|
| `--step rel` | `json_directory` | `output/json` | ✅ 正确读取统一目录 |
| `--step rel_llm` | `json_llm_directory` | `output/json_llm` | ❌ 读取废弃配置 |

#### 根本原因

**问题代码位置**: `metaweave/core/relationships/llm_relationship_discovery.py:220-221`

```python
# ❌ 当前代码（错误）
output_config = config.get("output", {})
json_llm_dir = output_config.get("json_llm_directory", "output/json_llm")
self.json_llm_dir = Path(json_llm_dir)
```

**配置文件现状**: `configs/metadata_config.yaml:263`

```yaml
# Step 2: 表/列画像输出配置
json_directory: output/json      # --step json 和 --step json_llm 统一输出目录
# json_llm_directory: output/json_llm  # 已废弃：json_llm 改为基于 json 的增强式处理
```

**对比**: `metaweave/core/relationships/pipeline.py:50-58`（正确实现）

```python
# ✅ rel 步骤的正确实现
output_config = self.config.get("output", {})
json_directory = output_config.get("json_directory")
if json_directory:
    self.json_dir = get_project_root() / json_directory
else:
    # Fallback: 从 output_dir 推导
    output_dir = output_config.get("output_dir", "output")
    self.json_dir = get_project_root() / output_dir / "json"
```

#### 后果分析

1. ❌ `rel_llm` 步骤会尝试读取 `output/json_llm` 目录
2. ❌ 如果该目录不存在，会抛出 `FileNotFoundError`
3. ❌ 即使目录存在，也会读取旧数据而非最新的统一 JSON

### ✅ 解决方案

#### 方案 1: 修复代码（推荐）

修改 `metaweave/core/relationships/llm_relationship_discovery.py:219-221`：

```python
# 修改前（第 219-221 行）
output_config = config.get("output", {})
json_llm_dir = output_config.get("json_llm_directory", "output/json_llm")
self.json_llm_dir = Path(json_llm_dir)

# 修改后（推荐实现）
output_config = config.get("output", {})
# 优先读取 json_directory，向后兼容 json_llm_directory
json_dir = output_config.get("json_directory") or \
           output_config.get("json_llm_directory", "output/json")
self.json_llm_dir = Path(json_dir)
```

**说明**：
- 优先读取新配置 `json_directory`
- 如果不存在，向后兼容旧配置 `json_llm_directory`
- 默认值改为 `output/json`
- 保持向后兼容性，不会破坏旧项目

#### 方案 2: 创建符号链接（临时）

Windows 环境：
```powershell
cd output
mklink /D json_llm json
```

Linux/macOS 环境：
```bash
cd output
ln -s json json_llm
```

**说明**：临时方案，让 `rel_llm` 可以通过 `json_llm` 目录访问到统一的 JSON 文件。

#### 方案 3: 临时恢复配置（不推荐）

```yaml
# configs/metadata_config.yaml
output:
  json_directory: output/json
  json_llm_directory: output/json  # 临时指向同一目录
```

**说明**：不推荐，因为这违背了配置简化的初衷。

### 🧪 修复后的验证步骤

```bash
# 1. 确认 JSON 文件存在
ls output/json/*.json

# 2. 测试 rel 步骤
metaweave metadata --config configs/metadata_config.yaml --step rel

# 3. 测试 rel_llm 步骤（修复代码后）
metaweave metadata --config configs/metadata_config.yaml --step rel_llm

# 4. 检查输出文件
ls output/rel/relationships_global.json
```

---

## 输出目录与格式对比

### 输出目录配置

两个命令使用**相同的输出目录配置**：

| 配置项 | `--step rel` | `--step rel_llm` |
|-------|-------------|-----------------|
| **配置键** | `rel_directory` | `rel_directory` |
| **默认目录** | `output/rel` | `output/rel` |
| **文件名** | `relationships_global.json` | `relationships_global.json` |
| **Markdown 输出** | `relationships_global.md` | ❌ 不生成 |
| **代码位置** | `writer.py:161` | `metadata_cli.py:347` |

### ⚠️ 文件覆盖风险

由于两个命令输出到**完全相同的文件路径**，后运行的命令会覆盖前一个命令的输出：

```bash
# 场景示例
metaweave metadata --step rel        # 生成: output/rel/relationships_global.json
metaweave metadata --step rel_llm    # 覆盖: output/rel/relationships_global.json ❌
```

### 输出格式对比

虽然文件名相同，但两个命令生成的 **JSON 格式结构存在差异**：

#### 元数据字段对比

| 字段 | `rel` 输出 | `rel_llm` 输出 |
|------|-----------|---------------|
| `metadata_source` | `"json_files"` | `"json_llm_files"` |
| `json_metadata_version` | ✅ `"2.0"` | ❌ 缺失 |
| `json_files_loaded` | ✅ 13 | ❌ 缺失 |
| `database_queries_executed` | ✅ 45 | ❌ 缺失 |
| `analysis_timestamp` | UTC (Z 结尾) | ISO 8601 (+00:00) |

#### 统计字段对比

| 统计字段 | `rel` | `rel_llm` |
|---------|-------|-----------|
| `total_relationships_found` | ✅ | ✅ |
| `foreign_key_relationships` | ✅ | ✅ |
| `composite_key_relationships` | ✅ | ❌ |
| `single_column_relationships` | ✅ | ❌ |
| `total_suppressed_single_relations` | ✅ | ❌ |
| `active_search_discoveries` | ✅ | ❌ |
| `dynamic_composite_discoveries` | ✅ | ❌ |
| `llm_assisted_relationships` | ❌ | ✅ |
| `rejected_low_confidence` | ❌ | ✅ (可选) |

#### 关系字段对比

| 字段 | `rel` | `rel_llm` | 说明 |
|------|-------|-----------|------|
| `relationship_id` | ✅ | ✅ | 格式一致 |
| `type` | ✅ | ✅ | `single_column` / `composite` |
| `discovery_method` | 多种类型 | 两种类型 | 见下方详情 |
| `cardinality` | ✅ | ✅ | `1:N` / `N:1` / `1:1` / `M:N` |
| `confidence_level` | ✅ | ✅ | `high` / `medium` / `low` |
| `composite_score` | ✅ | ✅ | 0.0-1.0 |
| `score_details` | ✅ | ✅ | 4 个评分维度 |
| `suppressed_single_relations` | ✅ 可能嵌套 | ❌ | 被抑制的单列关系 |

**`discovery_method` 值对比**：

| 命令 | 可能的值 |
|------|---------|
| `rel` | `foreign_key`, `active_search`, `composite_logical_key`, `composite_physical`, `dynamic_composite` |
| `rel_llm` | `foreign_key_constraint`, `llm_assisted` |

### 格式差异示例

#### `rel` 输出格式（详细版）

```json
{
  "metadata_source": "json_files",
  "json_metadata_version": "2.0",
  "json_files_loaded": 13,
  "database_queries_executed": 45,
  "analysis_timestamp": "2025-12-26T10:00:00Z",
  
  "statistics": {
    "total_relationships_found": 10,
    "foreign_key_relationships": 2,
    "composite_key_relationships": 3,
    "single_column_relationships": 5,
    "total_suppressed_single_relations": 8,
    "active_search_discoveries": 5,
    "dynamic_composite_discoveries": 3
  },
  
  "relationships": [
    {
      "relationship_id": "rel_abc123",
      "type": "single_column",
      "from_table": {"schema": "public", "table": "dim_region"},
      "to_table": {"schema": "public", "table": "dim_store"},
      "from_column": "region_id",
      "to_column": "region_id",
      "discovery_method": "active_search",
      "cardinality": "1:N",
      "confidence_level": "high",
      "composite_score": 0.85,
      "score_details": {
        "inclusion_rate": 0.95,
        "name_similarity": 1.0,
        "type_compatibility": 1.0,
        "jaccard_index": 0.88
      }
    }
  ]
}
```

#### `rel_llm` 输出格式（简化版）

```json
{
  "metadata_source": "json_llm_files",
  "analysis_timestamp": "2025-12-26T10:00:00+00:00",
  
  "statistics": {
    "total_relationships_found": 10,
    "foreign_key_relationships": 2,
    "llm_assisted_relationships": 8,
    "rejected_low_confidence": 3
  },
  
  "relationships": [
    {
      "relationship_id": "rel_abc123",
      "type": "single_column",
      "from_table": {"schema": "public", "table": "dim_region"},
      "to_table": {"schema": "public", "table": "dim_store"},
      "from_column": "region_id",
      "to_column": "region_id",
      "discovery_method": "llm_assisted",
      "cardinality": "1:N",
      "confidence_level": "high",
      "composite_score": 0.85,
      "score_details": {
        "inclusion_rate": 0.95,
        "name_similarity": 1.0,
        "type_compatibility": 1.0,
        "jaccard_index": 0.88
      }
    }
  ]
}
```

### 格式差异影响分析

**潜在问题**：

1. **文件覆盖** - 后运行的命令会覆盖前一个命令的结果
2. **元数据丢失** - `rel_llm` 输出缺少 `json_files_loaded` 等诊断信息
3. **统计不完整** - `rel_llm` 不区分复合键和单列关系的统计
4. **下游兼容性** - 依赖特定字段的工具可能失败

**代码位置**：
- `rel` 格式：`metaweave/core/relationships/writer.py:94-166` (`_write_json_v32`)
- `rel_llm` 格式：`metaweave/core/relationships/llm_relationship_discovery.py:934-964` (`_build_output`)

### 解决方案建议

#### 方案 1: 手动管理输出文件（推荐用于对比）

```bash
# 分别运行并重命名
metaweave metadata --step rel
mv output/rel/relationships_global.json output/rel/relationships_rel.json

metaweave metadata --step rel_llm
mv output/rel/relationships_global.json output/rel/relationships_rel_llm.json

# 对比差异
diff output/rel/relationships_rel.json output/rel/relationships_rel_llm.json
```

#### 方案 2: 使用不同配置文件

创建两个配置文件，指定不同的输出目录：

```yaml
# configs/metadata_config_rel.yaml
output:
  rel_directory: output/rel_traditional

# configs/metadata_config_rel_llm.yaml
output:
  rel_directory: output/rel_llm
```

```bash
metaweave metadata --config configs/metadata_config_rel.yaml --step rel
metaweave metadata --config configs/metadata_config_rel_llm.yaml --step rel_llm
```

#### 方案 3: 修改代码添加后缀

**修改 `metadata_cli.py:347`**（添加 `_llm` 后缀）：

```python
# 修改前
output_file = rel_dir / "relationships_global.json"

# 修改后
output_file = rel_dir / "relationships_global_llm.json"
```

**或修改 `writer.py:161`**（添加 `_traditional` 后缀）：

```python
# 修改前
json_file = self.rel_dir / f"relationships_{self.rel_granularity}.json"

# 修改后
json_file = self.rel_dir / f"relationships_{self.rel_granularity}_traditional.json"
```

#### 方案 4: 统一输出格式（长期方案）

让 `rel_llm` 步骤也使用 `RelationshipWriter` 生成 v3.2 格式，保持输出一致性：

**优点**：
- ✅ 格式统一，下游工具兼容性好
- ✅ 完整的统计信息和元数据
- ✅ 便于对比和分析

**缺点**：
- ⚠️ 需要重构 `rel_llm` 的输出逻辑
- ⚠️ 需要适配 `suppressed_single_relations` 等字段

---

## 字段依赖详细分析

### `--step rel` 模块依赖

#### 1. MetadataRepository

**依赖字段**：
```python
# repository.py:60-62
table_info = data.get("table_info", {})
schema_name = table_info.get("schema_name")
table_name = table_info.get("table_name")

# repository.py:99-104
table_profile = table_data.get("table_profile")
physical_constraints = table_profile.get("physical_constraints", {})
foreign_keys = physical_constraints.get("foreign_keys", [])
```

**状态**: ✅ 所有字段存在

#### 2. CandidateGenerator

**依赖字段**：
```python
# candidate_generator.py:113-114
source_info = source_table.get("table_info", {})
source_schema = source_info.get("schema_name")

# candidate_generator.py:183-184
table_profile = table.get("table_profile", {})
physical = table_profile.get("physical_constraints", {})

# candidate_generator.py:209-213
logical_keys = table_profile.get("logical_keys", {})
candidate_pks = logical_keys.get("candidate_primary_keys", [])

# candidate_generator.py 访问列信息
column_profiles = source_table.get("column_profiles", {})
```

**状态**: ✅ 所有字段存在

#### 3. RelationshipScorer

**依赖字段**：
```python
# scorer.py:193-202
source_info = source_table.get("table_info", {})
target_info = target_table.get("table_info", {})
source_profiles = source_table.get("column_profiles", {})
target_profiles = target_table.get("column_profiles", {})

# scorer.py 类型兼容性计算
source_col_data = source_profiles.get(src_col, {})
data_type = source_col_data.get("data_type")
```

**状态**: ✅ 所有字段存在

### `--step rel_llm` 模块依赖

#### 1. LLMRelationshipDiscovery

**依赖字段**：
```python
# llm_relationship_discovery.py:546-548
table_info = data.get("table_info", {})
full_name = f"{table_info['schema_name']}.{table_info['table_name']}"

# llm_relationship_discovery.py:597-602 (构建 LLM 提示词)
prompt = RELATIONSHIP_DISCOVERY_PROMPT.format(
    table1_name=table1_name,
    table1_json=json.dumps(table1, ensure_ascii=False, indent=2),  # ✅ 完整 JSON
    table2_name=table2_name,
    table2_json=json.dumps(table2, ensure_ascii=False, indent=2),
)
```

**关键点**: LLM 接收**完整的 JSON 内容**，包括：
- ✅ `table_info` - 表基本信息
- ✅ `column_profiles` - 列元数据（包括注释、类型、统计信息）
- ✅ `sample_records.records` - **样例数据**（LLM 分析的关键输入）
- ✅ `table_profile` - 物理约束、逻辑主键

**状态**: ✅ 所有字段存在，完整性 100%

#### 2. MetadataRepository（复用）

```python
# llm_relationship_discovery.py:227
self.repo = MetadataRepository(self.json_llm_dir, rel_id_salt=rel_id_salt)

# llm_relationship_discovery.py:355
fk_relation_objects, fk_relationship_ids = self.repo.collect_foreign_keys(tables)
```

**状态**: ✅ 与 `rel` 步骤使用相同逻辑，字段兼容

#### 3. RelationshipScorer（复用）

```python
# llm_relationship_discovery.py:736-739
score_details, cardinality = self.scorer._calculate_scores(
    from_table, from_columns,
    to_table, to_columns
)
```

**状态**: ✅ 与 `rel` 步骤使用相同评分逻辑，字段兼容

### 字段使用汇总表

| 字段 | `rel` 使用方式 | `rel_llm` 使用方式 | 必需性 |
|------|---------------|-------------------|--------|
| `table_info` | 表标识、日志输出 | 表标识、LLM 输入 | ✅ 必需 |
| `column_profiles` | 类型兼容性计算、候选生成 | LLM 输入（完整） | ✅ 必需 |
| `table_profile.physical_constraints` | 外键直通、候选生成 | 外键去重 | ✅ 必需 |
| `table_profile.logical_keys` | 逻辑主键候选生成 | 不直接使用 | ✅ rel 需要 |
| `sample_records.records` | 不使用 | LLM 推理数据源 | ✅ rel_llm 需要 |
| `semantic_analysis` | 不使用 | 不使用 | ⚪ 可选保留 |
| `role_specific_info` | 不使用 | 不使用 | ⚪ 可选保留 |
| `llm_enhanced_at` | 不使用 | 不使用 | ⚪ 标记字段 |

---

## 运行建议

### 推荐工作流

#### 工作流 1: 单独使用某个命令

```bash
# === 阶段 1: 生成统一的 JSON 元数据 ===
metaweave metadata --config configs/metadata_config.yaml --step json_llm
# 输出: output/json/*.json（包含所有字段）
# 耗时: 8-15 分钟（LLM 增强）

# === 阶段 2a: 使用传统算法发现关系 ===
metaweave metadata --config configs/metadata_config.yaml --step rel
# 输出: output/rel/relationships_global.json (详细格式)
# 输入: output/json/*.json（使用基础字段）
# 耗时: 2-5 分钟

# 或者

# === 阶段 2b: 使用 LLM 辅助发现关系（修复代码后）===
metaweave metadata --config configs/metadata_config.yaml --step rel_llm
# 输出: output/rel/relationships_global.json (简化格式)
# 输入: output/json/*.json（使用完整 JSON + 样例数据）
# 耗时: 可能几十分钟（取决于表数量和 LLM API 速度）
```

#### 工作流 2: 对比两个命令的结果

⚠️ **注意**：两个命令输出到相同文件，需要手动管理避免覆盖。

```bash
# 阶段 1: 生成 JSON 元数据
metaweave metadata --step json_llm

# 阶段 2a: 运行 rel 并保存结果
metaweave metadata --step rel
mv output/rel/relationships_global.json output/rel/relationships_rel.json
mv output/rel/relationships_global.md output/rel/relationships_rel.md

# 阶段 2b: 运行 rel_llm 并保存结果
metaweave metadata --step rel_llm
mv output/rel/relationships_global.json output/rel/relationships_rel_llm.json

# 阶段 3: 对比差异
diff output/rel/relationships_rel.json output/rel/relationships_rel_llm.json

# 或使用 jq 美化对比
jq . output/rel/relationships_rel.json > /tmp/rel.formatted.json
jq . output/rel/relationships_rel_llm.json > /tmp/rel_llm.formatted.json
diff /tmp/rel.formatted.json /tmp/rel_llm.formatted.json
```

### 性能和成本考虑

| 因素 | `rel` | `rel_llm` | 建议 |
|------|-------|-----------|------|
| **执行时间** | 2-5 分钟 | 可能几十分钟 | 开发用 `rel`，生产用 `rel_llm` |
| **API 成本** | 无 | 有（LLM 调用） | 评估 API 配额和预算 |
| **准确性** | 高（基于统计） | 更高（语义理解） | 复杂业务逻辑建议 `rel_llm` |
| **稳定性** | 极高 | 依赖 LLM 可用性 | CI/CD 使用 `rel` |
| **可解释性** | 强（评分明细） | 中（LLM 黑盒） | 需要审计场景用 `rel` |

### 混合使用策略

**场景 1: 渐进式增强**
```bash
# 1. 使用 rel 快速生成基础关系
metaweave metadata --step rel
# 2. 人工审核，标记复杂场景
# 3. 对特定表对使用 rel_llm 补充
```

**场景 2: 质量对比**
```bash
# 1. 分别运行两个命令，输出到不同文件
metaweave metadata --step rel
mv output/rel/relationships_global.json output/rel/rel_result.json

metaweave metadata --step rel_llm
mv output/rel/relationships_global.json output/rel/rel_llm_result.json

# 2. 对比差异，评估 LLM 的增量价值
```

### 故障排查

#### 问题 1: `rel_llm` 报错 "json_llm 目录不存在"

**解决**：
```bash
# 临时方案：创建符号链接
cd output && ln -s json json_llm

# 永久方案：修复代码（见上文）
```

#### 问题 2: `rel_llm` 返回空结果

**检查清单**：
1. ✅ JSON 文件中是否包含 `sample_records.records`
2. ✅ LLM API Key 是否配置正确
3. ✅ LLM API 配额是否充足
4. ✅ 查看日志中的 LLM 调用失败信息

#### 问题 3: 输出文件被覆盖

**现象**：运行第二个命令后，第一个命令的输出文件消失了。

**原因**：两个命令输出到相同的文件路径 `output/rel/relationships_global.json`。

**解决**：
```bash
# 方法 1: 运行后立即重命名
metaweave metadata --step rel
mv output/rel/relationships_global.json output/rel/rel_result.json

# 方法 2: 使用不同配置文件（见"输出目录与格式对比"章节）

# 方法 3: 修改代码添加文件名后缀（见"输出目录与格式对比"章节）
```

#### 问题 4: 两个命令结果差异很大

**正常现象**：
- `rel` 基于统计评分，更保守
- `rel_llm` 基于语义理解，可能发现更多潜在关系
- 建议人工审核差异部分，评估准确性

#### 问题 5: 下游工具读取 JSON 失败

**可能原因**：下游工具依赖 `rel` 特有的字段（如 `json_files_loaded`、`composite_key_relationships`），但读取了 `rel_llm` 生成的文件。

**解决**：
1. 确认使用的是正确命令生成的文件
2. 考虑修改下游工具，兼容两种格式
3. 或采用方案 4（统一输出格式）

---

## 附录

### A. JSON 文件结构示例

完整的 JSON 文件结构示例（`public.dim_company.json`）：

```json
{
  "metadata_version": "2.0",
  "generated_at": "2025-12-26T05:34:41.519200Z",
  "llm_enhanced_at": "2025-12-26T05:34:54.050816+00:00",
  
  "table_info": {
    "schema_name": "public",
    "table_name": "dim_company",
    "table_type": "table",
    "comment": "公司维表",
    "comment_source": "ddl",
    "total_rows": 3,
    "total_columns": 2
  },
  
  "column_profiles": {
    "company_id": {
      "column_name": "company_id",
      "ordinal_position": 1,
      "data_type": "integer",
      "is_nullable": false,
      "comment": "公司ID（主键）",
      "statistics": {
        "sample_count": 3,
        "unique_count": 3,
        "null_count": 0,
        "uniqueness": 1.0,
        "value_distribution": {"1": 1, "2": 1, "3": 1}
      },
      "semantic_analysis": {
        "semantic_role": "identifier",
        "semantic_confidence": 0.95
      },
      "structure_flags": {
        "is_primary_key": false,
        "is_unique": true,
        "is_nullable": false
      },
      "role_specific_info": {
        "identifier_info": {
          "naming_pattern": "logical_primary_key",
          "is_surrogate": true
        }
      }
    }
  },
  
  "table_profile": {
    "table_category": "dim",
    "confidence": 0.95,
    "physical_constraints": {
      "primary_key": null,
      "foreign_keys": [],
      "unique_constraints": [],
      "indexes": []
    },
    "logical_keys": {
      "candidate_primary_keys": [
        {
          "columns": ["company_id"],
          "confidence_score": 1.0,
          "uniqueness": 1.0,
          "null_rate": 0.0
        }
      ]
    }
  },
  
  "sample_records": {
    "sample_method": "random",
    "sample_size": 3,
    "total_rows": 3,
    "sampled_at": "2025-12-24T04:52:54.006772Z",
    "records": [
      {"company_id": 1, "company_name": "京东便利"},
      {"company_id": 2, "company_name": "喜士多"},
      {"company_id": 3, "company_name": "全家"}
    ]
  }
}
```

### B. 相关配置文件

**`configs/metadata_config.yaml`**（输出配置部分）：

```yaml
# 输出配置
output:
  output_dir: output

  # Step 2: 表/列画像输出配置
  json_directory: output/json      # --step json 和 --step json_llm 统一输出目录
  # json_llm_directory: output/json_llm  # 已废弃

  # Step 3: 关系发现输出配置
  rel_directory: output/rel        # --step rel/rel_llm 输出
  rel_granularity: global
  rel_id_salt: ""

  # Step 4: CQL 生成输出配置
  cql_directory: output/cql
```

### C. 代码文件索引

| 文件 | 关键类/函数 | 用途 |
|------|------------|------|
| `metaweave/cli/metadata_cli.py` | `metadata_command` | CLI 入口 |
| `metaweave/core/relationships/pipeline.py` | `RelationshipDiscoveryPipeline` | `rel` 步骤主控 |
| `metaweave/core/relationships/llm_relationship_discovery.py` | `LLMRelationshipDiscovery` | `rel_llm` 步骤主控 |
| `metaweave/core/relationships/repository.py` | `MetadataRepository` | JSON 加载和外键提取 |
| `metaweave/core/relationships/candidate_generator.py` | `CandidateGenerator` | 候选关系生成 |
| `metaweave/core/relationships/scorer.py` | `RelationshipScorer` | 关系评分（6 维度） |
| `metaweave/core/relationships/decision_engine.py` | `DecisionEngine` | 决策过滤 |

### D. 参考文档

- [json_vs_json_llm_对比分析.md](./json_vs_json_llm_对比分析.md) - JSON 步骤对比
- [1_rel_llm_关系发现LLM提示词模板.md](./1_rel_llm_关系发现LLM提示词模板.md) - LLM 提示词
- [命令依赖关系分析.md](./命令依赖关系分析.md) - 整体命令依赖

---

## 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|---------|
| 1.1 | 2025-12-26 | 新增"输出目录与格式对比"章节，详细分析输出格式差异和解决方案 |
| 1.0 | 2025-12-26 | 初始版本，完整评估 `rel` vs `rel_llm` 兼容性 |

---

**文档结束**

