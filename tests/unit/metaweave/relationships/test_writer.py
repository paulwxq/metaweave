"""测试RelationshipWriter模块"""

import json
import pytest
from pathlib import Path
from metaweave.core.relationships.writer import RelationshipWriter
from metaweave.core.relationships.models import Relation


class TestRelationshipWriter:
    """RelationshipWriter单元测试"""

    @pytest.fixture
    def temp_output_dir(self, tmp_path):
        """创建临时输出目录"""
        return tmp_path / "output" / "metaweave" / "metadata" / "rel"

    @pytest.fixture
    def config(self, temp_output_dir):
        """创建测试配置"""
        return {
            "database": {
                "database": "store_db"
            },
            "output": {
                "rel_directory": str(temp_output_dir),
                "rel_granularity": "global"
            },
            "decision": {
                "accept_threshold": 0.80,
                "high_confidence_threshold": 0.90,
                "medium_confidence_threshold": 0.80
            },
            "weights": {
                "inclusion_rate": 0.40,
                "name_similarity": 0.10,
                "comment_similarity": 0.10,
                "type_compatibility": 0.20,
                "jaccard_index": 0.20
            },
        }

    @pytest.fixture
    def writer(self, config):
        """创建Writer实例"""
        return RelationshipWriter(config)

    @pytest.fixture
    def sample_relations(self):
        """创建示例关系数据"""
        return [
            Relation(
                relationship_id="rel_abc123456789",
                source_schema="public",
                source_table="fact_sales",
                source_columns=["store_id"],
                target_schema="public",
                target_table="dim_store",
                target_columns=["store_id"],
                relationship_type="foreign_key",
                cardinality="N:1"
            ),
            Relation(
                relationship_id="rel_def123456789",
                source_schema="public",
                source_table="fact_sales",
                source_columns=["company_id"],
                target_schema="public",
                target_table="dim_company",
                target_columns=["company_id"],
                relationship_type="inferred",
                cardinality="N:1",
                composite_score=0.85,
                score_details={
                    "inclusion_rate": 0.8,
                    "name_similarity": 1.0,
                    "jaccard_index": 0.6,
                    "comment_similarity": 1.0,
                    "type_compatibility": 1.0
                },
                inference_method="rule_physical_key",
                candidate_origin="rule"
            )
        ]

    def test_write_json_output(self, writer, sample_relations, temp_output_dir, config):
        """测试JSON输出（v3.2格式）"""
        output_files = writer.write_results(sample_relations, [], config)

        # 检查文件是否生成
        json_file = temp_output_dir / f"{config['database']['database']}.relationships_global.json"
        assert json_file.exists()

        # 验证JSON内容（v3.2格式）
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 顶层字段验证
        assert data["json_metadata_version"] == "3.0"
        assert data["metadata_source"] == "json_files"
        assert data["database"] == config["database"]["database"]
        assert "generated_timestamp" in data
        assert data["generated_timestamp"].endswith("Z") is False
        assert "create_timestamp" not in data
        assert "analysis_timestamp" not in data
        assert data["json_files_loaded"] == 0  # 未传 tables，默认为空
        assert data["database_queries_executed"] == 0  # 未传 extra_statistics
        assert "statistics" in data
        assert "relationships" in data  # 不是 relations

        # 统计字段验证（v3.2格式，按开发指南 2.10 节要求）
        stats = data["statistics"]
        assert "total_relationships_found" in stats
        assert "foreign_key_relationships" in stats  # ← 新增验证
        assert "composite_key_relationships" in stats
        assert "single_column_relationships" in stats
        assert "total_suppressed_single_relations" in stats
        assert "rule_only_relationships" in stats
        assert "llm_only_relationships" in stats
        assert "rule_llm_overlap_relationships" in stats

        # 验证关系数据
        assert len(data["relationships"]) == 2
        assert data["relationships"][0]["relationship_id"] == "rel_abc123456789"
        assert data["relationships"][1]["composite_score"] == 0.85

        # 验证v3.2格式字段
        rel1 = data["relationships"][0]
        assert "type" in rel1
        assert "from_table" in rel1
        assert "to_table" in rel1
        assert isinstance(rel1["from_table"], dict)

        # 验证 cardinality 字段输出
        assert "cardinality" in rel1
        assert rel1["cardinality"] == "N:1"
        assert data["relationships"][1]["cardinality"] == "N:1"

        assert rel1["discovery_method"] == "foreign_key_constraint"
        assert rel1["composite_score"] == 1.0
        assert rel1["confidence_level"] == "high"
        assert "metrics" not in rel1
        assert data["relationships"][1]["metrics"]

    def test_write_markdown_output(self, writer, sample_relations, temp_output_dir, config):
        """测试Markdown输出"""
        output_files = writer.write_results(sample_relations, [], config)

        # 检查文件是否生成
        md_file = temp_output_dir / f"{config['database']['database']}.relationships_global.md"
        assert md_file.exists()

        # 验证Markdown内容
        with open(md_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "# 表间关系发现报告" in content or "表间关系" in content or "关系" in content
        assert f"database: {config['database']['database']}" in content
        assert "生成方式: rel" in content
        assert "统计" in content
        assert "fact_sales" in content
        assert "dim_store" in content

        # 标题下方不应有空行（仅检查 #/##/###）
        lines = content.splitlines()
        for idx, line in enumerate(lines[:-1]):
            if line.startswith("# ") or line.startswith("## ") or line.startswith("### "):
                assert lines[idx + 1].strip() != ""

        assert "- **关系类型**: foreign_key" in content
        assert "- **置信度**: 1.000 (高)" in content
        fk_block = content.split("### 2.")[0]
        assert "**评分明细**" not in fk_block
        assert "**推断方法**" not in fk_block

    def test_foreign_key_confidence_json_and_md_are_aligned(
        self, writer, sample_relations, temp_output_dir, config
    ):
        """外键置信度 1.0 由同一套 writer 逻辑写入 JSON 与 Markdown。"""
        output_files = writer.write_results(sample_relations, [], config)
        json_file = next(p for p in output_files if p.endswith(".json"))
        md_file = next(p for p in output_files if p.endswith(".md"))

        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        fk = next(r for r in data["relationships"] if r["discovery_method"] == "foreign_key_constraint")
        inferred = next(r for r in data["relationships"] if r.get("discovery_method") != "foreign_key_constraint")

        assert fk["composite_score"] == 1.0
        assert fk["confidence_level"] == "high"
        assert "metrics" not in fk
        assert inferred["composite_score"] == 0.85
        assert "metrics" in inferred

        md_content = Path(md_file).read_text(encoding="utf-8")
        assert "- **置信度**: 1.000 (高)" in md_content
        assert "- **置信度**: 0.850 (中)" in md_content
        assert "高置信度 (≥0.9): 1" in md_content or "高置信度 (≥0.90): 1" in md_content

    def test_generated_by_and_json_metadata_version_json_md_aligned(
        self, writer, sample_relations, temp_output_dir, config
    ):
        """generated_by / json_metadata_version 由同一套 writer 逻辑写入 JSON 与 Markdown。"""
        tables = {
            "public.users": {"metadata_version": "3.0", "table_info": {"table_name": "users"}},
            "public.orders": {"metadata_version": "3.0", "table_info": {"table_name": "orders"}},
        }
        output_files = writer.write_results(
            sample_relations, [], config,
            tables=tables,
            generated_by=RelationshipWriter.generated_by_label(True),
        )
        json_file = next(p for p in output_files if p.endswith(".json"))
        md_file = next(p for p in output_files if p.endswith(".md"))

        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["generated_by"] == "rel_llm"
        assert data["json_metadata_version"] == "3.0"

        md_content = Path(md_file).read_text(encoding="utf-8")
        assert "生成方式: rel_llm" in md_content

        output_files_off = writer.write_results(
            sample_relations, [], config,
            generated_by=RelationshipWriter.generated_by_label(False),
        )
        json_off = next(p for p in output_files_off if p.endswith(".json"))
        md_off = next(p for p in output_files_off if p.endswith(".md"))
        with open(json_off, "r", encoding="utf-8") as f:
            data_off = json.load(f)
        assert data_off["generated_by"] == "rel"
        assert data_off["json_metadata_version"] == "3.0"
        assert "生成方式: rel" in Path(md_off).read_text(encoding="utf-8")

    def test_generated_by_label(self):
        assert RelationshipWriter.generated_by_label(True) == "rel_llm"
        assert RelationshipWriter.generated_by_label(False) == "rel"

    def test_suppressed_embedded_in_composite(self, writer, temp_output_dir, config):
        """测试被抑制关系嵌入复合键（v3.2格式）"""
        # 创建复合键关系
        composite_relation = Relation(
            relationship_id="rel_composite_001",
            source_schema="public",
            source_table="fact_sales",
            source_columns=["store_id", "date_day"],
            target_schema="public",
            target_table="dim_store",
            target_columns=["store_id", "date_day"],
            relationship_type="inferred",
            cardinality="N:1",
            composite_score=0.90,
            score_details={},
            inference_method="rule_physical_key",
            candidate_origin="rule"
        )

        # 被抑制的单列关系
        suppressed = [
            {
                "source": {
                    "table_info": {"schema_name": "public", "table_name": "fact_sales"}
                },
                "target": {
                    "table_info": {"schema_name": "public", "table_name": "dim_store"}
                },
                "source_columns": ["store_id"],
                "target_columns": ["store_id"],
                "candidate_origin": "rule",
                "key_origin": "physical",
                "composite_score": 0.82,
                "score_details": {}
            }
        ]

        output_files = writer.write_results([composite_relation], suppressed, config)

        # 验证被抑制关系嵌入到复合键对象中
        json_file = temp_output_dir / f"{config['database']['database']}.relationships_global.json"
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 找到复合键关系
        composite_rels = [r for r in data["relationships"] if r["type"] == "composite"]
        assert len(composite_rels) == 1

        # 验证嵌入的被抑制关系
        assert "suppressed_single_relations" in composite_rels[0]
        suppressed_list = composite_rels[0]["suppressed_single_relations"]
        assert len(suppressed_list) == 1
        assert suppressed_list[0]["from_column"] == "store_id"
        assert suppressed_list[0]["to_column"] == "store_id"
        assert "original_score" in suppressed_list[0]
        assert "suppression_reason" in suppressed_list[0]

    def test_output_files_list(self, writer, sample_relations, config):
        """测试输出文件列表"""
        output_files = writer.write_results(sample_relations, [], config)

        # 应该至少有JSON和Markdown两个文件
        assert len(output_files) >= 2

        # 检查文件路径格式
        for file_path in output_files:
            assert "relationships_global" in file_path

    def test_statistics_in_json(self, writer, sample_relations, config):
        """测试JSON中的统计数据（v3.2格式，按开发指南 2.10 节要求）"""
        output_files = writer.write_results(sample_relations, [], config)

        json_file = Path(output_files[0])
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["json_files_loaded"] == 0  # 未传 tables
        assert data["database_queries_executed"] == 0  # 未传 extra_statistics

        stats = data["statistics"]
        # v3.2格式统计字段（完整7个字段）
        assert stats["total_relationships_found"] == 2
        assert stats["foreign_key_relationships"] == 1  # ← 新增验证
        assert stats["composite_key_relationships"] == 0
        assert stats["single_column_relationships"] == 2
        assert stats["total_suppressed_single_relations"] == 0
        # 来源分档统计（doc 15 §3.8）：sample_relations 中 1 条外键直通 +
        # 1 条 candidate_origin="rule" 的推断关系，无 LLM/重叠
        assert stats["rule_only_relationships"] == 1
        assert stats["llm_only_relationships"] == 0
        assert stats["rule_llm_overlap_relationships"] == 0

    def test_statistics_source_breakdown_all_four_buckets(self, writer, config):
        """P7 勘误回归测试（doc 15 §3.8）：来源分档统计要能区分
        物理FK / 仅规则 / 仅LLM / 重叠 四种情况，替代恒为 0 的旧口径
        （active_search_discoveries / dynamic_composite_discoveries）。
        """
        def _relation(rel_id, origin, table_suffix):
            return Relation(
                relationship_id=rel_id,
                source_schema="public",
                source_table=f"fact_{table_suffix}",
                source_columns=["id"],
                target_schema="public",
                target_table=f"dim_{table_suffix}",
                target_columns=["id"],
                relationship_type="inferred",
                cardinality="N:1",
                composite_score=0.85,
                score_details={},
                inference_method="rule_physical_key" if origin == "rule" else "llm_inferred",
                candidate_origin=origin,
            )

        fk_relation = Relation(
            relationship_id="rel_fk_001",
            source_schema="public",
            source_table="fact_fk",
            source_columns=["store_id"],
            target_schema="public",
            target_table="dim_fk",
            target_columns=["store_id"],
            relationship_type="foreign_key",
            cardinality="N:1",
        )

        relations = [
            fk_relation,
            _relation("rel_rule_001", "rule", "rule"),
            _relation("rel_llm_001", "llm", "llm"),
            _relation("rel_overlap_001", "rule+llm", "overlap"),
        ]

        output_files = writer.write_results(relations, [], config)
        json_file = Path(output_files[0])
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        stats = data["statistics"]
        assert stats["total_relationships_found"] == 4
        assert stats["foreign_key_relationships"] == 1
        assert stats["rule_only_relationships"] == 1
        assert stats["llm_only_relationships"] == 1
        assert stats["rule_llm_overlap_relationships"] == 1

        # 旧的恒为 0 死字段不应再出现在输出中
        assert "active_search_discoveries" not in stats
        assert "dynamic_composite_discoveries" not in stats

        # FK 关系不应携带 candidate_origin（见 Relation.to_dict 的 pop 逻辑）
        fk_output = next(r for r in data["relationships"] if r["discovery_method"] == "foreign_key_constraint")
        assert "candidate_origin" not in fk_output
        assert fk_output["composite_score"] == 1.0
        assert fk_output["confidence_level"] == "high"
        assert "metrics" not in fk_output

    def test_json_files_loaded_and_db_queries(self, writer, sample_relations, config):
        """测试 json_files_loaded 和 database_queries_executed 反映真实值"""
        tables = {
            "public.users": {"table_info": {"table_name": "users"}},
            "public.orders": {"table_info": {"table_name": "orders"}},
            "public.products": {"table_info": {"table_name": "products"}},
        }
        extra_statistics = {"database_queries_executed": 15}

        output_files = writer.write_results(
            sample_relations, [], config,
            tables=tables,
            extra_statistics=extra_statistics,
        )

        json_file = Path(output_files[0])
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["json_files_loaded"] == 3
        assert data["database_queries_executed"] == 15
        assert "database_queries_executed" not in data["statistics"]

    def test_write_results_does_not_mutate_extra_statistics(self, writer, sample_relations, config):
        """write_results() 不应修改调用方传入的 extra_statistics 字典"""
        extra_statistics = {
            "database_queries_executed": 9,
            "llm_assisted_relationships": 3,
            "rejected_low_confidence": 1,
        }
        original = extra_statistics.copy()

        writer.write_results(
            sample_relations, [], config,
            extra_statistics=extra_statistics,
        )

        assert extra_statistics == original

    def test_output_directory_creation(self, sample_relations, tmp_path, config):
        """测试输出目录自动创建"""
        # 使用一个新的、不存在的目录
        new_output_dir = tmp_path / "new_test_dir" / "rel"

        # 确保目录不存在
        assert not new_output_dir.exists()

        # 创建新的config和writer
        new_config = config.copy()
        new_config["output"] = {
            "rel_directory": str(new_output_dir),
            "rel_granularity": "global"
        }

        # 初始化writer时会创建目录
        new_writer = RelationshipWriter(new_config)

        # 目录应该在初始化时被创建
        assert new_output_dir.exists()

        # 写入结果
        new_writer.write_results(sample_relations, [], new_config)

        # 文件应该被创建
        assert (new_output_dir / f"{config['database']['database']}.relationships_global.json").exists()

    def test_discovery_method_mapping(self, writer, temp_output_dir, config):
        """测试 discovery_method, source_type, source_constraint 字段映射
        （v3 新分类体系，doc 15 §3.15：rule_physical_key / rule_logical_key / llm_inferred）
        """
        # 准备表元数据（v3：表级 physical_constraints / indexes，而非列级 structure_flags）
        tables = {
            "public.fact_sales": {
                "table_profile": {
                    "physical_constraints": {"primary_key": None, "unique_constraints": []},
                    "indexes": [
                        {"columns": ["store_id"], "is_unique": False, "condition": None}
                    ],
                }
            },
            "public.dim_store": {
                "table_profile": {
                    "physical_constraints": {
                        "primary_key": {"columns": ["store_id"]},
                        "unique_constraints": [],
                    },
                    "indexes": [],
                }
            },
            "public.fact_summary": {
                "table_profile": {
                    "physical_constraints": {"primary_key": None, "unique_constraints": []},
                    "indexes": [],
                    "unique_column_sets": [
                        {"columns": ["order_id", "product_id"], "confidence_score": 0.9}
                    ],
                }
            },
        }

        # 创建不同类型的推断关系
        relations = [
            # 规则候选：源键集为物理约束（单列索引，非 PK/UK）
            Relation(
                relationship_id="rel_001",
                source_schema="public",
                source_table="fact_sales",
                source_columns=["store_id"],
                target_schema="public",
                target_table="dim_store",
                target_columns=["store_id"],
                relationship_type="inferred",
                cardinality="N:1",
                composite_score=0.88,
                score_details={},
                inference_method="rule_physical_key"
            ),
            # 规则候选：源键集为逻辑键（复合）
            Relation(
                relationship_id="rel_003",
                source_schema="public",
                source_table="fact_sales",
                source_columns=["order_id", "product_id"],
                target_schema="public",
                target_table="fact_summary",
                target_columns=["order_id", "product_id"],
                relationship_type="inferred",
                cardinality="N:1",
                composite_score=0.85,
                score_details={},
                inference_method="rule_logical_key"
            ),
            # LLM 候选
            Relation(
                relationship_id="rel_004",
                source_schema="public",
                source_table="fact_sales",
                source_columns=["order_id", "line_id"],
                target_schema="public",
                target_table="fact_detail",
                target_columns=["order_id", "line_id"],
                relationship_type="inferred",
                cardinality="N:1",
                composite_score=0.90,
                score_details={},
                inference_method="llm_inferred"
            )
        ]

        # 通过 tables 参数传入表元数据
        output_files = writer.write_results(relations, [], config, tables=tables)

        # 验证JSON输出
        json_file = temp_output_dir / f"{config['database']['database']}.relationships_global.json"
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 验证规则候选（物理键，源列为单列索引，目标列为物理主键）
        rel1 = [r for r in data["relationships"] if r["relationship_id"] == "rel_001"][0]
        assert rel1["discovery_method"] == "physical_key_matching"
        assert rel1["target_source_type"] == "primary_key"
        assert rel1["source_constraint"] == "single_field_index"

        # 验证规则候选（逻辑键）
        rel3 = [r for r in data["relationships"] if r["relationship_id"] == "rel_003"][0]
        assert rel3["discovery_method"] == "logical_key_matching"
        assert rel3.get("target_source_type") is None  # 复合键不判定 target_source_type
        assert rel3.get("source_constraint") is None  # 复合键不判定 source_constraint

        # 验证 LLM 候选
        rel4 = [r for r in data["relationships"] if r["relationship_id"] == "rel_004"][0]
        assert rel4["discovery_method"] == "llm_inferred"
        assert rel4["target_source_type"] == "llm_inferred"
        assert rel4.get("source_constraint") is None

    def test_unknown_inference_method_raises(self, writer, config):
        """未知 inference_method（含旧值）不再回退 standard_matching，而是直接报错（doc 15 §3.15）"""
        relation = Relation(
            relationship_id="rel_unknown",
            source_schema="public",
            source_table="fact_sales",
            source_columns=["store_id"],
            target_schema="public",
            target_table="dim_store",
            target_columns=["store_id"],
            relationship_type="inferred",
            cardinality="N:1",
            composite_score=0.88,
            score_details={},
            inference_method="single_active_search"  # 旧值，v3 不再支持
        )

        with pytest.raises(ValueError):
            writer.write_results([relation], [], config)

    def test_schema_granularity_warning(self, sample_relations, tmp_path, config, caplog):
        """测试配置 schema 粒度时给出警告并强制使用 global"""
        import logging

        # 配置 schema 粒度
        schema_config = config.copy()
        schema_config["output"] = {
            "rel_directory": str(tmp_path / "rel"),
            "rel_granularity": "schema"  # ← 配置 schema
        }

        # 创建 writer（应该触发警告）
        with caplog.at_level(logging.WARNING):
            writer = RelationshipWriter(schema_config)

        # 验证警告信息
        assert any("仅支持 rel_granularity='global'" in record.message for record in caplog.records)
        assert any("schema" in record.message for record in caplog.records)

        # 验证强制使用 global
        assert writer.rel_granularity == "global"

        # 验证输出文件名仍然是 global
        writer.write_results(sample_relations, [], schema_config)
        assert (tmp_path / "rel" / f"{config['database']['database']}.relationships_global.json").exists()
        assert (tmp_path / "rel" / f"{config['database']['database']}.relationships_global.md").exists()

    def test_global_granularity_no_warning(self, sample_relations, tmp_path, config, caplog):
        """测试配置 global 粒度时不给出警告"""
        import logging

        # 配置 global 粒度（默认值）
        global_config = config.copy()
        global_config["output"] = {
            "rel_directory": str(tmp_path / "rel"),
            "rel_granularity": "global"
        }

        # 创建 writer（不应该触发警告）
        with caplog.at_level(logging.WARNING):
            writer = RelationshipWriter(global_config)

        # 验证没有警告
        assert not any("仅支持 rel_granularity='global'" in record.message for record in caplog.records)

        # 验证使用 global
        assert writer.rel_granularity == "global"

    def test_markdown_title_with_column_names(self, writer, temp_output_dir, config):
        """测试 Markdown 标题包含列名"""
        # 创建单列关系
        single_rel = Relation(
            relationship_id="rel_single_001",
            source_schema="public",
            source_table="dim_company",
            source_columns=["company_id"],
            target_schema="public",
            target_table="dim_store",
            target_columns=["company_id"],
            relationship_type="inferred",
            cardinality="N:1",
            composite_score=0.90,
            score_details={},
            inference_method="rule_physical_key"
        )

        # 创建复合键关系
        composite_rel = Relation(
            relationship_id="rel_composite_001",
            source_schema="public",
            source_table="fact_sales",
            source_columns=["store_id", "date_day"],
            target_schema="public",
            target_table="dim_store_calendar",
            target_columns=["store_id", "date_day"],
            relationship_type="inferred",
            cardinality="N:1",
            composite_score=0.92,
            score_details={},
            inference_method="rule_physical_key"
        )

        # 写入 Markdown
        writer.write_results([single_rel, composite_rel], [], config)

        # 读取 Markdown 文件
        md_file = temp_output_dir / f"{config['database']['database']}.relationships_global.md"
        with open(md_file, "r", encoding="utf-8") as f:
            content = f.read()

        # 验证单列关系标题包含列名
        assert "### 1. public.dim_company.company_id → public.dim_store.company_id" in content

        # 验证复合键关系标题包含列名（方括号格式）
        assert "### 2. public.fact_sales.[store_id, date_day] → public.dim_store_calendar.[store_id, date_day]" in content

    def test_cardinality_output_all_types(self, writer, temp_output_dir, config):
        """测试所有基数类型在 JSON 输出中的正确性"""
        # 创建不同基数类型的关系
        relations = [
            Relation(
                relationship_id="rel_1to1",
                source_schema="public",
                source_table="users",
                source_columns=["user_id"],
                target_schema="public",
                target_table="user_profiles",
                target_columns=["user_id"],
                relationship_type="inferred",
                cardinality="1:1",  # 一对一
                composite_score=0.95,
                score_details={},
                inference_method="rule_physical_key"
            ),
            Relation(
                relationship_id="rel_1toN",
                source_schema="public",
                source_table="departments",
                source_columns=["dept_id"],
                target_schema="public",
                target_table="employees",
                target_columns=["dept_id"],
                relationship_type="inferred",
                cardinality="1:N",  # 一对多
                composite_score=0.90,
                score_details={},
                inference_method="rule_physical_key"
            ),
            Relation(
                relationship_id="rel_Nto1",
                source_schema="public",
                source_table="orders",
                source_columns=["customer_id"],
                target_schema="public",
                target_table="customers",
                target_columns=["customer_id"],
                relationship_type="inferred",
                cardinality="N:1",  # 多对一
                composite_score=0.88,
                score_details={},
                inference_method="rule_physical_key"
            ),
            Relation(
                relationship_id="rel_MtoN",
                source_schema="public",
                source_table="students",
                source_columns=["student_id"],
                target_schema="public",
                target_table="courses",
                target_columns=["course_id"],
                relationship_type="inferred",
                cardinality="M:N",  # 多对多
                composite_score=0.75,
                score_details={},
                inference_method="rule_physical_key"
            ),
        ]

        output_files = writer.write_results(relations, [], config)

        # 验证 JSON 输出
        json_file = temp_output_dir / f"{config['database']['database']}.relationships_global.json"
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 验证每种基数类型
        rel_by_id = {r["relationship_id"]: r for r in data["relationships"]}

        assert rel_by_id["rel_1to1"]["cardinality"] == "1:1"
        assert rel_by_id["rel_1toN"]["cardinality"] == "1:N"
        assert rel_by_id["rel_Nto1"]["cardinality"] == "N:1"
        assert rel_by_id["rel_MtoN"]["cardinality"] == "M:N"
