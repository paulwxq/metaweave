# Cleanup: json_llm 文案残留清理

**日期**: 2025-12-26
**优先级**: 低优先级
**影响范围**: `metaweave/core/relationships/llm_relationship_discovery.py`

## 问题描述

### 发现过程
代码审查时发现，虽然已经将 `LLMRelationshipDiscovery` 的输入源从 `json_llm` 目录统一到 `json` 目录，但代码中仍有多处注释和文档字符串残留了 `json_llm` 的引用。

### 问题定位

**文件**: `metaweave/core/relationships/llm_relationship_discovery.py`

**残留位置**:
1. **模块文档字符串** (line 4)
2. **类文档字符串** (line 194)
3. **错误消息** (line 398)
4. **方法文档字符串** (line 682)
5. **返回值字段** (line 1070)

### 影响分析

1. **文档不一致**:
   - 代码注释与实际行为不一致
   - 可能误导开发者理解代码逻辑

2. **错误提示误导**:
   - 错误消息提示执行 `--step json_llm --domain`
   - 实际应该是 `--step json --domain`

3. **元数据标识混淆**:
   - 返回值中 `metadata_source: "json_llm_files"`
   - 实际来自 `json_files`

## 修复内容

### 修复 1: 模块文档字符串

**修复前**:
```python
"""LLM 辅助关联关系发现。

数据来源：
- LLM 调用：从 json_llm 文件读取，不查询数据库
- 评分阶段：复用 RelationshipScorer，需要数据库连接
"""
```

**修复后**:
```python
"""LLM 辅助关联关系发现。

数据来源：
- LLM 调用：从 json 文件读取表元数据，不查询数据库
- 评分阶段：复用 RelationshipScorer，需要数据库连接
"""
```

### 修复 2: 类文档字符串

**修复前**:
```python
class LLMRelationshipDiscovery:
    """LLM 辅助关联关系发现

    数据来源：
    - LLM 调用：从 json_llm 文件读取，不查询数据库
    - 评分阶段：复用 RelationshipScorer，需要数据库连接
    """
```

**修复后**:
```python
class LLMRelationshipDiscovery:
    """LLM 辅助关联关系发现

    数据来源：
    - LLM 调用：从 json 文件读取表元数据，不查询数据库
    - 评分阶段：复用 RelationshipScorer，需要数据库连接
    """
```

### 修复 3: 错误消息

**修复前**:
```python
logger.error(
    "以下表的 JSON 文件缺少 table_domains 属性，"
    "请先执行 --step json_llm --domain 生成："
)
```

**修复后**:
```python
logger.error(
    "以下表的 JSON 文件缺少 table_domains 属性，"
    "请先执行 --step json --domain 生成："
)
```

### 修复 4: 方法文档字符串

**修复前**:
```python
def _call_llm(self, table1: Dict, table2: Dict) -> List[Dict]:
    """调用 LLM 获取候选关联（带重试）

    注意：table1/table2 来自 json_llm 文件，不查询数据库
    """
```

**修复后**:
```python
def _call_llm(self, table1: Dict, table2: Dict) -> List[Dict]:
    """调用 LLM 获取候选关联（带重试）

    注意：table1/table2 来自 json 文件，不查询数据库
    """
```

### 修复 5: 返回值字段

**修复前**:
```python
return {
    "metadata_source": "json_llm_files",
    "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
    "statistics": stats,
    "relationships": relations
}
```

**修复后**:
```python
return {
    "metadata_source": "json_files",
    "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
    "statistics": stats,
    "relationships": relations
}
```

## 验证

执行 grep 搜索确认清理完成：

```bash
grep -n "json_llm" metaweave/core/relationships/llm_relationship_discovery.py
```

**结果**: 无匹配 ✅

## 其他文件说明

搜索发现其他文件中也有 `json_llm` 引用，但这些是**合理的引用**，无需修改：

### metadata_cli.py
- `--step json_llm`: 这是一个独立的命令，用于 LLM 增强 JSON 生成
- `--step cql_llm`: 这个命令仍使用 `json_llm_directory`
- 这些是**有意为之的功能**，不是残留引用

### 其他模块文件
- `json_llm_enhancer.py`: json_llm 功能的实现模块
- `llm_json_generator.py`: json_llm 功能的生成器
- 这些模块名称本身就包含 json_llm，是正确的

## 收益

### 修复前
- ❌ 文档与代码实现不一致
- ❌ 错误消息提示错误的命令
- ❌ 元数据标识与实际来源不符

### 修复后
- ✅ 文档准确反映代码行为
- ✅ 错误消息提示正确的命令
- ✅ 元数据标识正确（json_files）
- ✅ 代码可读性提升

## 总结

本次清理移除了 `LLMRelationshipDiscovery` 模块中5处残留的 `json_llm` 引用，确保文档、注释、错误消息与代码实现完全一致。这是输入源统一改造的收尾工作，提升了代码的可维护性和可读性。

**注意**: 其他模块中的 `json_llm` 引用均为合理的功能引用，保持不变。
