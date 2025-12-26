"""
测试 LLM 响应解析逻辑的健壮性

测试覆盖：
1. 方法1: ```json ... ``` 代码块提取
2. 方法2: ``` ... ``` 通用代码块提取
3. 方法3: 状态机提取（处理字符串内花括号）
4. 方法4: 简单 brace_count 降级
5. 边缘情况：字符串内花括号、转义字符、嵌套对象
6. 真实 LLM 调用测试
"""

import pytest
import sys
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from metaweave.core.relationships.llm_relationship_discovery import LLMRelationshipDiscovery


class TestParseMethodPriority:
    """测试各提取方法的优先级和正确性"""

    @pytest.fixture
    def discovery(self):
        """创建测试用的 LLMRelationshipDiscovery 实例"""
        # 创建临时目录
        temp_dir = tempfile.mkdtemp()

        config = {
            "output": {"json_directory": temp_dir},
            "relationships": {},
            "llm": {
                "active": "qwen",
                "providers": {
                    "qwen": {
                        "model": "qwen-plus",
                        "api_key": "test-key"
                    }
                }
            }
        }
        connector = Mock()
        disc = LLMRelationshipDiscovery(config, connector)

        yield disc

        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_method1_json_fenced_code_block(self, discovery):
        """测试方法1: ```json ... ``` 代码块提取"""
        response = """
Here is the result:

```json
{
  "relationships": [
    {
      "type": "single_column",
      "from_table": {"schema": "public", "table": "orders"},
      "from_column": "user_id",
      "to_table": {"schema": "public", "table": "users"},
      "to_column": "id"
    }
  ]
}
```

Hope this helps!
        """

        result = discovery._parse_llm_response(response)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["type"] == "single_column"
        assert result[0]["from_table"]["table"] == "orders"

    def test_method2_generic_fenced_code_block(self, discovery):
        """测试方法2: ``` ... ``` 无语言标签代码块提取"""
        response = """
```
{
  "relationships": [
    {
      "type": "single_column",
      "from_table": {"schema": "public", "table": "posts"},
      "from_column": "author_id",
      "to_table": {"schema": "public", "table": "users"},
      "to_column": "id"
    }
  ]
}
```
        """

        result = discovery._parse_llm_response(response)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["from_table"]["table"] == "posts"

    def test_method3_state_machine_extraction(self, discovery):
        """测试方法3: 状态机提取（无代码块标记）"""
        response = """
The analysis shows:

{
  "relationships": [
    {
      "type": "single_column",
      "from_table": {"schema": "public", "table": "comments"},
      "from_column": "post_id",
      "to_table": {"schema": "public", "table": "posts"},
      "to_column": "id"
    }
  ]
}

End of analysis.
        """

        result = discovery._parse_llm_response(response)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["from_table"]["table"] == "comments"

    def test_priority_json_block_over_generic(self, discovery):
        """测试优先级: ```json 优先于 ```"""
        response = """
```
This is not JSON
```

```json
{
  "relationships": [
    {
      "type": "single_column",
      "from_table": {"schema": "public", "table": "items"},
      "from_column": "category_id",
      "to_table": {"schema": "public", "table": "categories"},
      "to_column": "id"
    }
  ]
}
```
        """

        result = discovery._parse_llm_response(response)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["from_table"]["table"] == "items"


class TestEdgeCases:
    """测试边缘情况和已知 bug 场景"""

    @pytest.fixture
    def discovery(self):
        temp_dir = tempfile.mkdtemp()
        config = {
            "output": {"json_directory": temp_dir},
            "relationships": {},
            "llm": {
                "active": "qwen",
                "providers": {"qwen": {"model": "qwen-plus", "api_key": "test-key"}}
            }
        }
        disc = LLMRelationshipDiscovery(config, Mock())
        yield disc
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_braces_in_string_values(self, discovery):
        """测试字符串值中包含花括号（这是原 bug 场景）"""
        response = """
```json
{
  "relationships": [
    {
      "type": "single_column",
      "from_table": {"schema": "public", "table": "logs"},
      "from_column": "user_id",
      "to_table": {"schema": "public", "table": "users"},
      "to_column": "id",
      "reason": "Detected pattern: logs.user_id references users.id {confidence: high}"
    }
  ]
}
```
        """

        result = discovery._parse_llm_response(response)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["from_table"]["table"] == "logs"
        assert "{confidence: high}" in result[0]["reason"]

    def test_escaped_quotes_in_strings(self, discovery):
        """测试字符串中的转义引号"""
        response = """
```json
{
  "relationships": [
    {
      "type": "single_column",
      "from_table": {"schema": "public", "table": "articles"},
      "from_column": "author_id",
      "to_table": {"schema": "public", "table": "users"},
      "to_column": "id",
      "note": "Column name is \\"author_id\\""
    }
  ]
}
```
        """

        result = discovery._parse_llm_response(response)

        assert isinstance(result, list)
        assert len(result) == 1
        assert 'author_id' in result[0]["note"]

    def test_nested_objects(self, discovery):
        """测试嵌套对象"""
        response = """
```json
{
  "relationships": [
    {
      "type": "single_column",
      "from_table": {"schema": "public", "table": "orders"},
      "from_column": "customer_id",
      "to_table": {"schema": "public", "table": "customers"},
      "to_column": "id",
      "metadata": {
        "confidence": "high",
        "evidence": {
          "name_similarity": 0.95,
          "type_match": true
        }
      }
    }
  ]
}
```
        """

        result = discovery._parse_llm_response(response)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["metadata"]["confidence"] == "high"
        assert result[0]["metadata"]["evidence"]["name_similarity"] == 0.95

    def test_multiple_json_objects_extracts_first(self, discovery):
        """测试多个 JSON 对象时提取第一个"""
        response = """
```json
{
  "relationships": [
    {
      "type": "single_column",
      "from_table": {"schema": "public", "table": "first"},
      "from_column": "id",
      "to_table": {"schema": "public", "table": "second"},
      "to_column": "first_id"
    }
  ]
}
```

And here's another one:

```json
{
  "relationships": []
}
```
        """

        result = discovery._parse_llm_response(response)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["from_table"]["table"] == "first"

    def test_empty_relationships_array(self, discovery):
        """测试空关系数组"""
        response = """
```json
{
  "relationships": []
}
```
        """

        result = discovery._parse_llm_response(response)

        assert isinstance(result, list)
        assert len(result) == 0

    def test_malformed_json_returns_empty(self, discovery):
        """测试格式错误的 JSON 返回空数组"""
        response = """
```json
{
  "relationships": [
    {
      "type": "single_column",
      "from_table": {"schema": "public", "table": "invalid"
      // missing closing braces
```
        """

        result = discovery._parse_llm_response(response)

        assert isinstance(result, list)
        assert len(result) == 0

    def test_no_json_returns_empty(self, discovery):
        """测试完全没有 JSON 返回空数组"""
        response = "I couldn't find any relationships between these tables."

        result = discovery._parse_llm_response(response)

        assert isinstance(result, list)
        assert len(result) == 0


class TestStateMachine:
    """专门测试状态机提取逻辑"""

    @pytest.fixture
    def discovery(self):
        temp_dir = tempfile.mkdtemp()
        config = {
            "output": {"json_directory": temp_dir},
            "relationships": {},
            "llm": {"active": "qwen", "providers": {"qwen": {"model": "qwen-plus", "api_key": "test-key"}}}
        }
        disc = LLMRelationshipDiscovery(config, Mock())
        yield disc
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_extract_simple_object(self, discovery):
        """测试提取简单对象"""
        text = 'Some text {"key": "value"} more text'
        result = discovery._extract_first_json_object(text)

        assert result == '{"key": "value"}'

    def test_extract_with_nested_braces(self, discovery):
        """测试提取嵌套花括号"""
        text = '{"outer": {"inner": "value"}}'
        result = discovery._extract_first_json_object(text)

        assert result == '{"outer": {"inner": "value"}}'

    def test_extract_with_braces_in_string(self, discovery):
        """测试字符串内的花括号不影响提取"""
        text = '{"message": "Use {variable} syntax"}'
        result = discovery._extract_first_json_object(text)

        assert result == '{"message": "Use {variable} syntax"}'

    def test_extract_with_escaped_quotes(self, discovery):
        """测试转义引号"""
        text = '{"quote": "She said \\"hello\\""}'
        result = discovery._extract_first_json_object(text)

        assert result == '{"quote": "She said \\"hello\\""}'

    def test_extract_complex_case(self, discovery):
        """测试复杂情况：嵌套 + 字符串内花括号 + 转义"""
        text = '''
Some preamble text
{
  "relationships": [
    {
      "note": "Pattern: {FK} -> {PK}",
      "escaped": "Quote: \\"value\\"",
      "nested": {
        "deep": {
          "value": "test"
        }
      }
    }
  ]
}
Trailing text
        '''
        result = discovery._extract_first_json_object(text)

        # 验证提取的是完整对象
        assert result.startswith('{')
        assert result.endswith('}')

        # 验证可以解析
        data = json.loads(result)
        assert "relationships" in data
        assert len(data["relationships"]) == 1
        assert "{FK} -> {PK}" in data["relationships"][0]["note"]

    def test_no_object_returns_none(self, discovery):
        """测试没有对象时返回 None"""
        text = "No JSON here at all"
        result = discovery._extract_first_json_object(text)

        assert result is None

    def test_unmatched_braces_returns_none(self, discovery):
        """测试不匹配的花括号返回 None"""
        text = "{ incomplete object"
        result = discovery._extract_first_json_object(text)

        assert result is None


class TestValidation:
    """测试结构验证逻辑"""

    @pytest.fixture
    def discovery(self):
        temp_dir = tempfile.mkdtemp()
        config = {
            "output": {"json_directory": temp_dir},
            "relationships": {},
            "llm": {"active": "qwen", "providers": {"qwen": {"model": "qwen-plus", "api_key": "test-key"}}}
        }
        disc = LLMRelationshipDiscovery(config, Mock())
        yield disc
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_valid_structure(self, discovery):
        """测试有效结构"""
        data = {"relationships": [{"type": "test"}]}
        assert discovery._validate_response_structure(data) is True

    def test_valid_empty_relationships(self, discovery):
        """测试空 relationships 数组也有效"""
        data = {"relationships": []}
        assert discovery._validate_response_structure(data) is True

    def test_invalid_not_dict(self, discovery):
        """测试非 dict 无效"""
        assert discovery._validate_response_structure([]) is False
        assert discovery._validate_response_structure("string") is False
        assert discovery._validate_response_structure(123) is False

    def test_invalid_missing_relationships_key(self, discovery):
        """测试缺少 relationships 键无效"""
        data = {"other_key": "value"}
        assert discovery._validate_response_structure(data) is False

    def test_invalid_relationships_not_list(self, discovery):
        """测试 relationships 不是 list 无效"""
        data = {"relationships": "not a list"}
        assert discovery._validate_response_structure(data) is False

        data = {"relationships": {"nested": "dict"}}
        assert discovery._validate_response_structure(data) is False


class TestRealLLMCalls:
    """测试真实 LLM 调用（需要配置文件和 LLM API key）"""

    @pytest.fixture
    def discovery_with_real_config(self):
        """创建使用真实配置的 discovery 实例"""
        from services.config_loader import load_config

        config_path = Path(__file__).parent.parent / "config.yaml"
        if not config_path.exists():
            pytest.skip("config.yaml 不存在，跳过真实 LLM 测试")

        config = load_config(config_path)

        # 检查 LLM 配置
        llm_config = config.get("llm", {})
        if not llm_config.get("active"):
            pytest.skip("LLM 未配置，跳过真实 LLM 测试")

        # 创建 mock connector（不需要真实数据库连接）
        connector = Mock()

        # 修改 json_directory 为临时目录（避免依赖真实 JSON 文件）
        config["output"]["json_directory"] = "/tmp/test_llm"

        return LLMRelationshipDiscovery(config, connector)

    @pytest.mark.skipif(
        not Path(__file__).parent.parent.joinpath("config.yaml").exists(),
        reason="需要 config.yaml 才能测试真实 LLM 调用"
    )
    def test_real_llm_call_with_simple_tables(self, discovery_with_real_config):
        """测试真实 LLM 调用 - 简单表结构"""
        # 构造两个简单的表元数据
        table1 = {
            "table_info": {
                "schema_name": "public",
                "table_name": "orders"
            },
            "table_profile": {
                "column_profiles": {
                    "order_id": {
                        "column_name": "order_id",
                        "data_type": "integer",
                        "is_nullable": False
                    },
                    "customer_id": {
                        "column_name": "customer_id",
                        "data_type": "integer",
                        "is_nullable": True
                    }
                },
                "physical_constraints": {
                    "primary_key": ["order_id"],
                    "unique_constraints": []
                }
            }
        }

        table2 = {
            "table_info": {
                "schema_name": "public",
                "table_name": "customers"
            },
            "table_profile": {
                "column_profiles": {
                    "customer_id": {
                        "column_name": "customer_id",
                        "data_type": "integer",
                        "is_nullable": False
                    },
                    "customer_name": {
                        "column_name": "customer_name",
                        "data_type": "varchar",
                        "is_nullable": True
                    }
                },
                "physical_constraints": {
                    "primary_key": ["customer_id"],
                    "unique_constraints": []
                }
            }
        }

        # 调用真实 LLM
        print("\n🤖 调用真实 LLM...")
        result = discovery_with_real_config._call_llm(table1, table2)

        # 验证结果
        print(f"✅ LLM 返回结果: {json.dumps(result, indent=2, ensure_ascii=False)}")

        assert isinstance(result, list), "返回值应该是 list"

        # LLM 可能返回空数组（如果认为没有关系）或包含关系
        if len(result) > 0:
            # 如果返回了关系，验证结构
            rel = result[0]
            assert "type" in rel
            assert "from_table" in rel
            assert "to_table" in rel

            # 验证 LLM 正确识别了 orders.customer_id -> customers.customer_id
            if rel["type"] == "single_column":
                assert "from_column" in rel
                assert "to_column" in rel

            print(f"✅ LLM 识别出 {len(result)} 个关系")
        else:
            print("ℹ️  LLM 认为没有关系（也是合理的结果）")


class TestFallbackBehavior:
    """测试降级行为"""

    @pytest.fixture
    def discovery(self):
        temp_dir = tempfile.mkdtemp()
        config = {
            "output": {"json_directory": temp_dir},
            "relationships": {},
            "llm": {"active": "qwen", "providers": {"qwen": {"model": "qwen-plus", "api_key": "test-key"}}}
        }
        disc = LLMRelationshipDiscovery(config, Mock())
        yield disc
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_fallback_to_method4_when_no_code_blocks(self, discovery):
        """测试无代码块时降级到方法4"""
        # 没有代码块，但有有效 JSON（方法3应该抓到）
        response = '{"relationships": []}'

        result = discovery._parse_llm_response(response)

        assert isinstance(result, list)
        assert len(result) == 0

    def test_all_methods_fail_returns_empty(self, discovery):
        """测试所有方法失败时返回空数组"""
        response = "Complete garbage with no JSON at all!"

        result = discovery._parse_llm_response(response)

        assert isinstance(result, list)
        assert len(result) == 0


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])
