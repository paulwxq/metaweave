"""测试外键约束名称是否正确传递到最终输出

测试目标：
1. 验证 JSON 文件中的 constraint_name 被正确提取
2. 验证 Relation 对象保留 constraint_name
3. 验证关系 JSON 文件包含 constraint_name
4. 验证 CQL 文件中的 JOIN_ON 关系包含 constraint_name

测试数据：使用 dvdrental 数据库的真实数据
"""

import json
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_json_has_constraint_name():
    """测试 1: JSON 文件中是否包含 constraint_name"""
    json_file = project_root / "output/json/dvdrental.public.address.json"
    
    if not json_file.exists():
        print("❌ 测试 1 失败: JSON 文件不存在")
        return False
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    foreign_keys = data.get("table_profile", {}).get("physical_constraints", {}).get("foreign_keys", [])
    
    if not foreign_keys:
        print("❌ 测试 1 失败: 没有找到外键")
        return False
    
    fk = foreign_keys[0]
    constraint_name = fk.get("constraint_name")
    
    if constraint_name == "fk_address_city":
        print(f"✅ 测试 1 通过: JSON 文件包含 constraint_name = '{constraint_name}'")
        return True
    else:
        print(f"❌ 测试 1 失败: constraint_name = {constraint_name}")
        return False


def test_relationship_json_has_constraint_name():
    """测试 2: 关系 JSON 文件中是否包含 constraint_name"""
    rel_file = project_root / "output/rel/dvdrental.relationships_global.json"
    
    if not rel_file.exists():
        print("❌ 测试 2 失败: 关系 JSON 文件不存在")
        return False
    
    with open(rel_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    relationships = data.get("relationships", [])
    
    if not relationships:
        print("❌ 测试 2 失败: 没有找到关系")
        return False
    
    # 查找 address -> city 的关系
    target_rel = None
    for rel in relationships:
        from_table = rel.get("from_table", {})
        to_table = rel.get("to_table", {})
        if (from_table.get("table") == "address" and 
            to_table.get("table") == "city" and
            rel.get("from_column") == "city_id"):
            target_rel = rel
            break
    
    if not target_rel:
        print("❌ 测试 2 失败: 没有找到 address -> city 关系")
        return False
    
    constraint_name = target_rel.get("constraint_name")
    
    if constraint_name == "fk_address_city":
        print(f"✅ 测试 2 通过: 关系 JSON 包含 constraint_name = '{constraint_name}'")
        return True
    elif constraint_name is None:
        print(f"❌ 测试 2 失败: constraint_name 是 None（BUG：外键约束名称丢失）")
        return False
    else:
        print(f"❌ 测试 2 失败: constraint_name = {constraint_name}")
        return False


def test_cql_file_has_constraint_name():
    """测试 3: CQL 文件中是否包含 constraint_name"""
    cql_file = project_root / "output/cql/import_all.dvdrental.cypher"
    
    if not cql_file.exists():
        print("❌ 测试 3 失败: CQL 文件不存在")
        return False
    
    with open(cql_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 查找 address -> city 关系的 JSON 数据
    import re
    # 查找包含 source_table: "public.address" 和 target_table: "public.city" 的块
    pattern = r'\{\s*"source_table":\s*"public\.address".*?"target_table":\s*"public\.city".*?"constraint_name":\s*("fk_address_city"|null)'
    
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        print("❌ 测试 3 失败: 未找到 address -> city 关系")
        return False
    
    constraint_value = match.group(1)
    
    if constraint_value == '"fk_address_city"':
        print(f"✅ 测试 3 通过: CQL 文件包含 constraint_name = 'fk_address_city'")
        return True
    elif constraint_value == 'null':
        print(f"❌ 测试 3 失败: constraint_name 是 null（BUG：外键约束名称未传递）")
        return False
    else:
        print(f"❌ 测试 3 失败: constraint_name = {constraint_value}")
        return False


def test_neo4j_property_exists():
    """测试 4: 检查 Neo4j 中是否会存储 constraint_name 属性（理论测试）"""
    print("\n📋 测试 4: Neo4j 属性存储行为说明")
    print("=" * 60)
    print("⚠️  Neo4j 行为说明：")
    print("   - 当属性值为非 null 时：属性会被存储")
    print("   - 当属性值为 null 时：属性不会被创建（节省空间）")
    print("")
    print("✅ 预期行为：")
    print("   - 如果 constraint_name = 'fk_address_city'")
    print("     → Neo4j 会存储该属性")
    print("   - 如果 constraint_name = null")
    print("     → Neo4j 不会创建该属性（查询时返回 null）")
    print("=" * 60)
    return True


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("🧪 外键约束名称传递测试")
    print("=" * 60)
    print("")
    
    results = []
    
    print("📝 测试 1: JSON 文件中的 constraint_name")
    print("-" * 60)
    results.append(test_json_has_constraint_name())
    print("")
    
    print("📝 测试 2: 关系 JSON 文件中的 constraint_name")
    print("-" * 60)
    results.append(test_relationship_json_has_constraint_name())
    print("")
    
    print("📝 测试 3: CQL 文件中的 constraint_name")
    print("-" * 60)
    results.append(test_cql_file_has_constraint_name())
    print("")
    
    test_neo4j_property_exists()
    print("")
    
    # 汇总结果
    print("=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"通过: {passed}/{total}")
    
    if passed == total:
        print("✅ 所有测试通过！")
        return 0
    else:
        print("❌ 存在失败的测试")
        print("")
        print("🐛 问题诊断：")
        print("-" * 60)
        if results[0] and not results[1]:
            print("问题出在：Relation 对象创建时未传递 constraint_name")
            print("修复位置：metaweave/core/relationships/repository.py")
            print("修复方法：在创建 Relation 时添加 constraint_name 参数")
        elif results[1] and not results[2]:
            print("问题出在：CQL 生成时未包含 constraint_name")
            print("修复位置：metaweave/core/cql_generator/writer.py")
        return 1


if __name__ == "__main__":
    sys.exit(main())

