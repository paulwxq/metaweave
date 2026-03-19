import pytest
from metaweave.core.relationships.type_compatibility import get_type_compatibility_score, meets_type_compatibility_threshold

def test_type_compatibility():
    # 至少覆盖：
    # 1. varchar <-> text：兼容 (0.85)
    assert get_type_compatibility_score("varchar", "text") == 0.85
    # 2. integer <-> bigint：兼容 (0.9)
    assert get_type_compatibility_score("integer", "bigint") == 0.9
    # 3. integer <-> numeric：兼容 (0.9)
    assert get_type_compatibility_score("integer", "numeric") == 0.9
    # 4. integer <-> float：低分 (0.6)
    assert get_type_compatibility_score("integer", "float") == 0.6
    # 5. varchar <-> integer：不兼容 (0.0)
    assert get_type_compatibility_score("varchar", "integer") == 0.0
    # 6. date <-> timestamp：部分兼容 (0.5)
    assert get_type_compatibility_score("date", "timestamp") == 0.5
    # 7. uuid <-> uuid：兼容 (1.0)
    assert get_type_compatibility_score("uuid", "uuid") == 1.0
    # 8. uuid <-> varchar：不兼容 (0.0)
    assert get_type_compatibility_score("uuid", "varchar") == 0.0
    # 9. boolean <-> integer：弱兼容 (0.6)
    assert get_type_compatibility_score("boolean", "integer") == 0.6

    # Test threshold helper
    assert meets_type_compatibility_threshold("varchar", "text", 0.8) is True
    assert meets_type_compatibility_threshold("varchar", "integer", 0.8) is False
