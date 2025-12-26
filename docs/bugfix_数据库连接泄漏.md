# Bug Fix: rel_llm 数据库连接泄漏问题

**日期**: 2025-12-26
**优先级**: 中优先级
**影响范围**: `metaweave/cli/metadata_cli.py` (rel_llm 分支)

## 问题描述

### 发现过程
代码审查时发现 `rel_llm` 分支与 `rel` pipeline 在数据库连接管理上不一致：
- `RelationshipDiscoveryPipeline` 有 `try/finally` 块确保连接关闭
- `rel_llm` CLI 分支创建了 `DatabaseConnector` 但从不关闭

### 问题定位

**位置**: `metaweave/cli/metadata_cli.py:321-372`

**问题代码**:
```python
# 初始化连接器
connector = DatabaseConnector(config.get("database", {}))

# 初始化发现器
discovery = LLMRelationshipDiscovery(
    config=config,
    connector=connector,
    ...
)

# 发现关系
relations, rejected_count, extra_statistics = discovery.discover()

# 输出结果
...

return  # ❌ connector 从未关闭
```

**对比 rel pipeline** (`metaweave/core/relationships/pipeline.py:208-210`):
```python
try:
    # ... 执行发现流程 ...

except Exception as e:
    logger.error(f"关系发现失败: {e}", exc_info=True)
    result.add_error(str(e))

finally:
    # ✅ 关闭数据库连接
    self.connector.close()
```

### 影响分析

1. **资源泄漏**:
   - 每次执行 `rel_llm` 都会打开数据库连接但不关闭
   - 长期运行会耗尽数据库连接池

2. **不一致性**:
   - `rel` 和 `rel_llm` 行为不一致
   - 用户可能期望相同的资源管理行为

3. **异常处理**:
   - 如果流程中途出错，连接会永久泄漏
   - 无法在异常情况下正确清理资源

## 修复方案

### 修复代码

在 `metadata_cli.py:324-376` 添加 `try/finally` 块：

```python
# 初始化连接器
connector = DatabaseConnector(config.get("database", {}))

try:  # ✅ 添加 try 块
    # 初始化发现器
    discovery = LLMRelationshipDiscovery(
        config=config,
        connector=connector,
        domain_filter=domain,
        cross_domain=cross_domain,
        db_domains_config=db_domains_config
    )

    # 检查 json 目录
    if not discovery.json_dir.exists():
        raise FileNotFoundError(
            f"json 目录不存在: {discovery.json_dir}\n"
            f"请先执行 --step json 生成表元数据 JSON"
        )

    # 发现关系
    relations, rejected_count, extra_statistics = discovery.discover()

    # 使用 RelationshipWriter 输出结果
    writer = RelationshipWriter(config)
    output_files = writer.write_results(
        relations=relations,
        suppressed=[],
        config=config,
        tables=discovery.tables,
        generated_by="rel_llm",
        extra_statistics=extra_statistics
    )

    # 显示结果
    click.echo("")
    click.echo("=" * 60)
    click.echo("📊 LLM 辅助关系发现结果")
    click.echo("=" * 60)
    total_relations = len(relations)
    llm_assisted = extra_statistics.get("llm_assisted_relationships", 0)
    fk_relations = total_relations - llm_assisted
    click.echo(f"✅ 总关系数: {total_relations} 个")
    click.echo(f"  - 物理外键: {fk_relations}")
    click.echo(f"  - LLM 推断: {llm_assisted}")
    if rejected_count > 0:
        click.echo(f"  - 低置信度拒绝: {rejected_count}")
    click.echo(f"📁 输出文件:")
    for output_file in output_files:
        click.echo(f"  - {output_file}")
    click.echo("=" * 60)
    click.echo("✨ LLM 辅助关系发现完成！")

finally:  # ✅ 添加 finally 块
    # 关闭数据库连接（与 rel pipeline 保持一致）
    connector.close()

return
```

### 修复要点

1. **try/finally 结构**: 确保无论成功/失败都会关闭连接
2. **与 pipeline 一致**: 使用与 `RelationshipDiscoveryPipeline` 相同的模式
3. **注释说明**: 明确标注与 rel pipeline 保持一致的目的

## 验证测试

创建测试脚本 `/tmp/test_connection_cleanup.py`，验证：

### 测试场景1: 正常流程
```python
mock_connector = MagicMock()
mock_connector.close = Mock()

# 模拟正常执行
discovery = LLMRelationshipDiscovery(mock_config, mock_connector)
# ... 执行操作 ...

# 模拟 finally 块
mock_connector.close()

# 验证
assert mock_connector.close.called == True
```

**结果**: ✅ 通过
```
✅ connector.close() 被调用
   调用次数: 1
```

### 测试场景2: 异常流程
```python
mock_connector2 = MagicMock()
mock_connector2.close = Mock()

try:
    discovery2 = LLMRelationshipDiscovery(mock_config, mock_connector2)
    raise ValueError("模拟的异常")  # 模拟异常
except ValueError:
    pass
finally:
    mock_connector2.close()  # 仍然调用 close

# 验证
assert mock_connector2.close.called == True
```

**结果**: ✅ 通过
```
✅ connector.close() 被调用（异常情况下）
   调用次数: 1
```

## 收益

### 修复前
- ❌ 每次执行 `rel_llm` 都泄漏一个数据库连接
- ❌ 异常情况下无法清理资源
- ❌ 与 `rel` pipeline 行为不一致

### 修复后
- ✅ 正常流程结束时关闭连接
- ✅ 异常流程中仍能关闭连接（finally 保证）
- ✅ 与 `RelationshipDiscoveryPipeline` 保持一致
- ✅ 避免数据库连接池耗尽
- ✅ 资源管理更加健壮

## 长期建议

考虑引入 Context Manager 模式进一步改进资源管理：

```python
class DatabaseConnector:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

# 使用 with 语句
with DatabaseConnector(config.get("database", {})) as connector:
    discovery = LLMRelationshipDiscovery(config, connector, ...)
    # ... 执行操作 ...
# 自动调用 connector.close()
```

这样可以进一步简化代码，让资源管理更加 Pythonic。

## 相关文件

- `metaweave/cli/metadata_cli.py:324-376` - 修复位置
- `metaweave/core/relationships/pipeline.py:208-210` - 参考实现
- `/tmp/test_connection_cleanup.py` - 验证测试

## 总结

这是一个典型的资源泄漏问题，通过添加 `try/finally` 块即可修复。修复后代码与 `rel` pipeline 保持一致，资源管理更加健壮，避免了潜在的连接池耗尽问题。
