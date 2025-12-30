import pandas as pd

from metaweave.core.metadata.models import (
    ColumnInfo,
    ForeignKey,
    PrimaryKey,
    TableMetadata,
)
from metaweave.core.metadata.profiler import MetadataProfiler


def _build_metadata():
    metadata = TableMetadata(
        schema_name="public",
        table_name="fact_sales",
        comment="店铺销售日流水事实表",
    )
    metadata.columns = [
        ColumnInfo(column_name="store_id", ordinal_position=1, data_type="integer", is_nullable=False),
        ColumnInfo(column_name="date_day", ordinal_position=2, data_type="date", is_nullable=False),
        ColumnInfo(column_name="amount", ordinal_position=3, data_type="numeric", is_nullable=False),
    ]
    metadata.primary_keys = [PrimaryKey(constraint_name="pk_fact_sales", columns=["store_id", "date_day"])]
    metadata.foreign_keys = [
        ForeignKey(
            constraint_name="fk_sales_store",
            source_columns=["store_id"],
            target_schema="public",
            target_table="dim_store",
            target_columns=["store_id"],
        )
    ]
    return metadata


def test_profiler_generates_column_and_table_profiles():
    metadata = _build_metadata()
    df = pd.DataFrame(
        {
            "store_id": [1, 2, 3, 1],
            "date_day": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-02", "2024-01-01"]),
            "amount": [100, 120, 130, 110],
        }
    )

    profiler = MetadataProfiler()
    result = profiler.profile(metadata, df)

    assert "store_id" in result.column_profiles
    store_profile = result.column_profiles["store_id"]
    assert store_profile.semantic_role == "identifier"
    assert store_profile.structure_flags.is_foreign_key

    amount_profile = result.column_profiles["amount"]
    assert amount_profile.semantic_role == "metric"
    assert amount_profile.metric_info is not None

    assert result.table_profile is not None
    assert result.table_profile.table_category == "fact"


def test_complex_takes_precedence_over_audit():
    """测试 audit_log (jsonb) 被识别为 complex，而非 audit"""
    from metaweave.core.metadata.models import StructureFlags

    profiler = MetadataProfiler()
    column = ColumnInfo(
        column_name="audit_log",
        ordinal_position=1,
        data_type="jsonb",
        is_nullable=True,
    )

    # Create a StructureFlags object with no physical constraints
    struct_flags = StructureFlags(
        is_primary_key=False,
        is_composite_primary_key_member=False,
        is_foreign_key=False,
        is_composite_foreign_key_member=False,
        is_unique=False,
        is_composite_unique_member=False,
        is_unique_constraint=False,
        is_composite_unique_constraint_member=False,
        is_indexed=False,
        is_composite_indexed_member=False,
        is_nullable=True,
    )

    role, confidence, *rest = profiler._classify_semantics(column, None, struct_flags)

    assert role == "complex", f"Expected 'complex' but got '{role}' for audit_log (jsonb)"
    assert confidence == 0.95


def test_complex_array_type():
    """测试 tags (text[]) 被识别为 complex"""
    from metaweave.core.metadata.models import StructureFlags

    profiler = MetadataProfiler()
    column = ColumnInfo(
        column_name="tags",
        ordinal_position=1,
        data_type="text[]",
        is_nullable=True,
    )

    # Create a StructureFlags object with no physical constraints
    struct_flags = StructureFlags(
        is_primary_key=False,
        is_composite_primary_key_member=False,
        is_foreign_key=False,
        is_composite_foreign_key_member=False,
        is_unique=False,
        is_composite_unique_member=False,
        is_unique_constraint=False,
        is_composite_unique_constraint_member=False,
        is_indexed=False,
        is_composite_indexed_member=False,
        is_nullable=True,
    )

    role, confidence, *rest = profiler._classify_semantics(column, None, struct_flags)

    assert role == "complex", f"Expected 'complex' but got '{role}' for tags (text[])"


def test_audit_still_works_for_non_complex_types():
    """测试非 complex 类型的 audit 字段仍能正确识别"""
    from metaweave.core.metadata.models import StructureFlags

    profiler = MetadataProfiler()

    # Test 1: created_at (timestamp) - should be audit (audit has priority over datetime in new order)
    column1 = ColumnInfo(
        column_name="created_at",
        ordinal_position=1,
        data_type="timestamp",
        is_nullable=False,
    )

    struct_flags1 = StructureFlags(
        is_primary_key=False,
        is_composite_primary_key_member=False,
        is_foreign_key=False,
        is_composite_foreign_key_member=False,
        is_unique=False,
        is_composite_unique_member=False,
        is_unique_constraint=False,
        is_composite_unique_constraint_member=False,
        is_indexed=False,
        is_composite_indexed_member=False,
        is_nullable=False,
    )

    role1, *rest1 = profiler._classify_semantics(column1, None, struct_flags1)
    assert role1 == "audit", f"Expected 'audit' but got '{role1}' for created_at (timestamp)"

    # Test 2: is_deleted (boolean) - should be audit
    column2 = ColumnInfo(
        column_name="is_deleted",
        ordinal_position=1,
        data_type="boolean",
        is_nullable=False,
    )

    struct_flags2 = StructureFlags(
        is_primary_key=False,
        is_composite_primary_key_member=False,
        is_foreign_key=False,
        is_composite_foreign_key_member=False,
        is_unique=False,
        is_composite_unique_member=False,
        is_unique_constraint=False,
        is_composite_unique_constraint_member=False,
        is_indexed=False,
        is_composite_indexed_member=False,
        is_nullable=False,
    )

    role2, *rest2 = profiler._classify_semantics(column2, None, struct_flags2)
    assert role2 == "audit", f"Expected 'audit' but got '{role2}' for is_deleted (boolean)"
