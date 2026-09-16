"""doc 18 CQL 阈值过滤与 relationship_id 边身份测试

覆盖 docs/update/18_CQL置信度阈值过滤设计.md §6 的核心用例：
- 阈值过滤（FK 按 discovery_method 豁免、边界、非法值含 bool/NaN/inf）
- relationship_id 校验（含首尾空白）
- 关系结构校验（type/cardinality/discovery_method/字段/zip 截断防御）
- 推断分数校验（拒 bool、有限、[0,1]）
- 规范化载荷比较与同 ID 冲突（含低分被过滤仍报冲突）
- 边身份去重、跨文件、双 FK 同表对、顺序无关
- 六项统计与恒等式
"""

import json
from pathlib import Path

import pytest

from metaweave.core.cql_generator.models import RelationshipFilterStats
from metaweave.core.cql_generator.reader import JSONReader
from metaweave.core.cql_generator.generator import CQLGenerator


def _make_reader(tmp_path, rels_by_file, threshold=0.9):
    """构造 JSONReader:tmp_path 下生成 json/ 与 rel/ 目录及指定 rel 文件"""
    json_dir = tmp_path / "json"
    json_dir.mkdir(exist_ok=True)
    rel_dir = tmp_path / "rel"
    rel_dir.mkdir(exist_ok=True)
    for fname, rels in rels_by_file.items():
        (rel_dir / fname).write_text(
            json.dumps({"relationships": rels}), encoding="utf-8"
        )
    return JSONReader(
        json_dir, rel_dir, composite_score_threshold=threshold
    )


def _rel(rel_id, src_table, dst_table, src_col, dst_col,
         method="llm_inferred", score=0.95, cardinality="N:1", **kwargs):
    rel = {
        "relationship_id": rel_id,
        "type": "single_column",
        "from_table": {"schema": "public", "table": src_table},
        "to_table": {"schema": "public", "table": dst_table},
        "from_column": src_col,
        "to_column": dst_col,
        "discovery_method": method,
        "cardinality": cardinality,
        **kwargs,
    }
    if method != "foreign_key_constraint":
        rel["composite_score"] = score
    return rel


class TestThresholdValidation:
    """generator 阈值校验（doc 18 §3）"""

    @pytest.mark.parametrize("bad", [True, False, "0.9", None, float("nan"),
                                     float("inf"), float("-inf"), -0.1, 1.5])
    def test_invalid_threshold_rejected(self, bad):
        with pytest.raises(ValueError):
            CQLGenerator._validate_threshold(bad)

    @pytest.mark.parametrize("good", [0, 0.5, 1, 0.9])
    def test_valid_threshold_accepted(self, good):
        assert CQLGenerator._validate_threshold(good) == float(good)


class TestThresholdFilter:
    """阈值过滤（doc 18 §2.1/§2.2）"""

    def test_inferred_below_threshold_filtered(self, tmp_path):
        reader = _make_reader(tmp_path, {
            "a.relationships_global.json": [
                _rel("rel_low", "orders", "products", "pid", "id", score=0.85),
                _rel("rel_high", "orders", "users", "uid", "id", score=0.95),
            ],
        }, threshold=0.9)
        joins, stats = reader._read_relationships()
        assert len(joins) == 1
        assert joins[0].relationship_id == "rel_high"
        assert stats.candidate_count == 2
        assert stats.threshold_passed_count == 1
        assert stats.threshold_filtered_count == 1
        assert stats.final_count == 1

    def test_score_equal_to_threshold_kept(self, tmp_path):
        reader = _make_reader(tmp_path, {
            "a.relationships_global.json": [_rel("rel_eq", "a", "b", "x", "y", score=0.9)],
        }, threshold=0.9)
        joins, stats = reader._read_relationships()
        assert len(joins) == 1

    def test_fk_exempt_even_with_low_score(self, tmp_path):
        """FK 按 discovery_method 豁免,与分数无关(doc 18 §2.1)"""
        reader = _make_reader(tmp_path, {
            "a.relationships_global.json": [
                _rel("rel_fk", "orders", "products", "pid", "id",
                     method="foreign_key_constraint", score=0.1),
            ],
        }, threshold=0.9)
        joins, stats = reader._read_relationships()
        assert len(joins) == 1
        assert stats.threshold_filtered_count == 0


class TestInputValidation:
    """输入校验失败路径（doc 18 §2.2/§2.3）"""

    def test_relationship_id_validation(self, tmp_path):
        cases = [
            _rel(None, "a", "b", "x", "y"),
            _rel("", "a", "b", "x", "y"),
            _rel("   ", "a", "b", "x", "y"),
            _rel(123, "a", "b", "x", "y"),
            _rel(" rel_abc ", "a", "b", "x", "y"),  # 首尾空白 → 报错不裁剪
        ]
        for rel in cases:
            reader = _make_reader(tmp_path, {"a.relationships_global.json": [rel]})
            with pytest.raises(ValueError, match="relationship_id"):
                reader._read_relationships()

    def test_structure_validation_type(self, tmp_path):
        for bad_type in [None, "single", "SINGLE_COLUMN"]:
            rel = _rel("rel_1", "a", "b", "x", "y")
            rel["type"] = bad_type
            reader = _make_reader(tmp_path, {"a.relationships_global.json": [rel]})
            with pytest.raises(ValueError, match="type"):
                reader._read_relationships()

    def test_structure_validation_cardinality(self, tmp_path):
        # 缺失
        rel_missing = _rel("rel_1", "a", "b", "x", "y")
        del rel_missing["cardinality"]
        reader = _make_reader(tmp_path, {"a.relationships_global.json": [rel_missing]})
        with pytest.raises(ValueError, match="cardinality"):
            reader._read_relationships()
        # 1:N 违反 doc 19 输出契约
        reader = _make_reader(tmp_path, {"a.relationships_global.json": [
            _rel("rel_2", "a", "b", "x", "y", cardinality="1:N")]})
        with pytest.raises(ValueError, match="cardinality"):
            reader._read_relationships()

    def test_structure_validation_discovery_method(self, tmp_path):
        for bad in [None, "", "   ", 42]:
            rel = _rel("rel_1", "a", "b", "x", "y")
            rel["discovery_method"] = bad
            reader = _make_reader(tmp_path, {"a.relationships_global.json": [rel]})
            with pytest.raises(ValueError, match="discovery_method"):
                reader._read_relationships()

    def test_structure_validation_zip_truncation_defense(self, tmp_path):
        """复合两侧字段数量不一致 → 报错,不静默截断"""
        rel = {
            "relationship_id": "rel_c",
            "type": "composite",
            "from_table": {"schema": "public", "table": "a"},
            "to_table": {"schema": "public", "table": "b"},
            "from_columns": ["a1", "a2"],
            "to_columns": ["b1"],
            "discovery_method": "llm_inferred",
            "composite_score": 0.9,
            "cardinality": "N:1",
        }
        reader = _make_reader(tmp_path, {"a.relationships_global.json": [rel]})
        with pytest.raises(ValueError, match="数量不一致"):
            reader._read_relationships()

    def test_structure_validation_blank_field_value(self, tmp_path):
        rel = _rel("rel_1", "a", "b", "   ", "y")
        reader = _make_reader(tmp_path, {"a.relationships_global.json": [rel]})
        with pytest.raises(ValueError, match="from_column"):
            reader._read_relationships()

    def test_structure_validation_non_dict_table_endpoints(self, tmp_path):
        """from_table/to_table 为字符串或数字 → 结构校验 ValueError,
        不是 AttributeError"""
        for bad in ["public.orders", 123]:
            rel = _rel("rel_1", "a", "b", "x", "y")
            rel["from_table"] = bad
            reader = _make_reader(tmp_path, {"a.relationships_global.json": [rel]})
            with pytest.raises(ValueError, match="from_table 必须是对象"):
                reader._read_relationships()

    def test_score_validation(self, tmp_path):
        bad_scores = [None, "0.9", True, False, float("nan"),
                      float("inf"), -0.1, 1.5]
        for score in bad_scores:
            rel = _rel("rel_1", "a", "b", "x", "y")
            rel["composite_score"] = score
            reader = _make_reader(tmp_path, {"a.relationships_global.json": [rel]})
            with pytest.raises(ValueError, match="composite_score"):
                reader._read_relationships()

    def test_fk_score_not_validated(self, tmp_path):
        """FK 直通分数缺失/非法也不校验(doc 18 §2.2)"""
        # helper 对 FK 直通不生成 composite_score 键 → 即"分数缺失"场景
        rel = _rel("rel_fk", "a", "b", "x", "y",
                   method="foreign_key_constraint")
        reader = _make_reader(tmp_path, {"a.relationships_global.json": [rel]})
        joins, stats = reader._read_relationships()
        assert len(joins) == 1


class TestDedupAndConflict:
    """边身份去重与同 ID 冲突（doc 18 §2.3）"""

    def test_same_table_pair_different_ids_both_kept(self, tmp_path):
        """同表对不同 relationship_id(双字段映射)→ 全部保留"""
        reader = _make_reader(tmp_path, {"a.relationships_global.json": [
            _rel("rel_ship", "orders", "addresses", "shipping_address_id", "id"),
            _rel("rel_bill", "orders", "addresses", "billing_address_id", "id"),
        ]})
        joins, stats = reader._read_relationships()
        assert len(joins) == 2
        assert {j.relationship_id for j in joins} == {"rel_ship", "rel_bill"}

    def test_identical_duplicates_deduped(self, tmp_path):
        reader = _make_reader(tmp_path, {"a.relationships_global.json": [
            _rel("rel_dup", "a", "b", "x", "y"),
            _rel("rel_dup", "a", "b", "x", "y"),
        ]})
        joins, stats = reader._read_relationships()
        assert len(joins) == 1
        assert stats.duplicate_group_count == 1
        assert stats.duplicate_discarded_count == 1
        assert stats.final_count == 1

    def test_cross_file_duplicates_deduped(self, tmp_path):
        reader = _make_reader(tmp_path, {
            "a.relationships_global.json": [_rel("rel_dup", "a", "b", "x", "y")],
            "b.relationships_global.json": [_rel("rel_dup", "a", "b", "x", "y")],
        })
        joins, stats = reader._read_relationships()
        assert len(joins) == 1
        assert stats.duplicate_group_count == 1

    def test_same_id_conflicting_payload_raises(self, tmp_path):
        reader = _make_reader(tmp_path, {
            "a.relationships_global.json": [_rel("rel_123", "a", "b", "x", "y", cardinality="N:1")],
            "b.relationships_global.json": [_rel("rel_123", "a", "b", "x", "y", cardinality="1:1")],
        })
        with pytest.raises(ValueError, match="冲突"):
            reader._read_relationships()

    def test_same_id_conflict_detected_before_filtering(self, tmp_path):
        """同 ID 两条分数不同、低分在阈值之下 → 仍报冲突(冲突检查先于过滤)"""
        reader = _make_reader(tmp_path, {
            "a.relationships_global.json": [_rel("rel_123", "a", "b", "x", "y", score=0.95)],
            "b.relationships_global.json": [_rel("rel_123", "a", "b", "x", "y", score=0.85)],
        }, threshold=0.9)
        with pytest.raises(ValueError, match="冲突"):
            reader._read_relationships()

    def test_canonical_payload_pair_order_insensitive(self, tmp_path):
        """A(a,b)->B(x,y) 与 A(b,a)->B(y,x) 载荷一致(doc 18 §2.3)"""
        rel_1 = {
            "relationship_id": "rel_c",
            "type": "composite",
            "from_table": {"schema": "public", "table": "a"},
            "to_table": {"schema": "public", "table": "b"},
            "from_columns": ["a1", "a2"],
            "to_columns": ["b1", "b2"],
            "discovery_method": "llm_inferred",
            "composite_score": 0.9,
            "cardinality": "N:1",
        }
        rel_2 = dict(rel_1)
        rel_2["from_columns"] = ["a2", "a1"]
        rel_2["to_columns"] = ["b2", "b1"]
        reader = _make_reader(tmp_path, {
            "a.relationships_global.json": [rel_1],
            "b.relationships_global.json": [rel_2],
        })
        joins, stats = reader._read_relationships()
        assert len(joins) == 1
        assert stats.duplicate_group_count == 1

    def test_fk_score_difference_not_a_conflict(self, tmp_path):
        """FK 分数差异不报冲突(doc 18 §2.3)"""
        rel_1 = _rel("rel_fk", "a", "b", "x", "y",
                     method="foreign_key_constraint", score=1.0)
        rel_2 = dict(rel_1, composite_score=0.5)
        reader = _make_reader(tmp_path, {
            "a.relationships_global.json": [rel_1],
            "b.relationships_global.json": [rel_2],
        })
        joins, stats = reader._read_relationships()
        assert len(joins) == 1


class TestOrderIndependence:
    """顺序无关性（doc 18 §6）"""

    def test_file_order_and_list_order_irrelevant(self, tmp_path):
        rels_a = [
            _rel("rel_b", "b", "a", "x", "y"),
            _rel("rel_a", "a", "b", "x", "y"),
        ]
        reader_1 = _make_reader(tmp_path, {
            "a.relationships_global.json": rels_a,
            "b.relationships_global.json": [_rel("rel_c", "c", "d", "x", "y")],
        })
        reader_2 = _make_reader(tmp_path, {
            "b.relationships_global.json": [_rel("rel_c", "c", "d", "x", "y")],
            "a.relationships_global.json": list(reversed(rels_a)),
        })
        joins_1, _ = reader_1._read_relationships()
        joins_2, _ = reader_2._read_relationships()
        assert [j.relationship_id for j in joins_1] == [
            j.relationship_id for j in joins_2
        ]
        # 按 relationship_id 字典序输出
        assert [j.relationship_id for j in joins_1] == ["rel_a", "rel_b", "rel_c"]


class TestStatsInvariants:
    """六项统计与恒等式（doc 18 §5）"""

    def test_stats_invariants(self, tmp_path):
        reader = _make_reader(tmp_path, {
            "a.relationships_global.json": [
                _rel("rel_fk", "a", "b", "x", "y",
                     method="foreign_key_constraint"),
                _rel("rel_dup", "c", "d", "x", "y"),
                _rel("rel_dup", "c", "d", "x", "y"),
                _rel("rel_low", "e", "f", "x", "y", score=0.5),
            ],
        }, threshold=0.9)
        joins, stats = reader._read_relationships()
        assert len(joins) == 2
        assert stats.candidate_count == 4
        assert stats.threshold_passed_count == 3
        assert stats.threshold_filtered_count == 1
        assert stats.duplicate_group_count == 1
        assert stats.duplicate_discarded_count == 1
        assert stats.final_count == 2
        # 恒等式
        assert stats.candidate_count == (
            stats.threshold_passed_count + stats.threshold_filtered_count
        )
        assert stats.final_count == (
            stats.threshold_passed_count - stats.duplicate_discarded_count
        )

    def test_empty_rel_dir_returns_zero_stats(self, tmp_path):
        reader = _make_reader(tmp_path, {})
        joins, stats = reader._read_relationships()
        assert joins == []
        assert stats == RelationshipFilterStats()


class TestWriteMetadataConsistency:
    """write_metadata 的统计一致性(doc 18 §5)"""

    def test_mismatched_stats_raises_value_error(self, tmp_path):
        """join_on_rels 与 filter_stats.final_count 不一致 → 显式 ValueError
        (不用 assert,-O 下会被删除)"""
        from metaweave.core.cql_generator.models import JOINOnRelation, TableNode
        from metaweave.core.cql_generator.writer import CypherWriter

        writer = CypherWriter(tmp_path)
        join_on_rels = [
            JOINOnRelation(
                relationship_id="rel_1",
                src_full_name="public.a",
                dst_full_name="public.b",
                cardinality="N:1",
            )
        ]
        with pytest.raises(ValueError, match="不一致"):
            writer.write_metadata(
                tables=[TableNode(full_name="public.a", schema="public", name="a")],
                columns=[],
                has_column_rels=[],
                join_on_rels=join_on_rels,
                step_name="cql",
                json_dir=tmp_path,
                rel_dir=tmp_path,
                filter_stats=RelationshipFilterStats(),  # final_count=0 但 join_on=1
            )


class TestConfigStructure:
    """配置文件结构回归:新增 cql_generation 不得破坏 output 节点(doc 18 实施回归)"""

    def test_output_keys_remain_under_output(self):
        import yaml
        from metaweave.utils.file_utils import get_project_root

        config_path = get_project_root() / "configs" / "metadata_config.yaml"
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))

        # 这些键必须属于 output(曾因 cql_generation 插入位置错误被吞入)
        for key in ("markdown_directory", "formats", "ddl_options", "markdown_options"):
            assert key in cfg["output"], f"output.{key} 缺失或被错误归属"

        # cql_generation 只包含阈值
        assert set(cfg["cql_generation"].keys()) == {"composite_score_threshold"}
