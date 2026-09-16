"""测试MetadataRepository模块"""

import json
import pytest
from pathlib import Path
from metaweave.core.relationships.repository import MetadataRepository


class TestMetadataRepository:
    """MetadataRepository单元测试"""

    def test_generate_relation_id_deterministic(self):
        """测试relationship_id生成的确定性"""
        repo = MetadataRepository(Path("output/json"))

        rel_id1 = repo._generate_relation_id(
            "public", "fact_sales", ["store_id"],
            "public", "dim_store", ["store_id"]
        )

        rel_id2 = repo._generate_relation_id(
            "public", "fact_sales", ["store_id"],
            "public", "dim_store", ["store_id"]
        )

        # 相同输入应生成相同ID
        assert rel_id1 == rel_id2
        assert rel_id1.startswith("rel_")
        assert len(rel_id1) == 16  # rel_ + 12位哈希

    def test_generate_relation_id_different_tables(self):
        """测试不同表生成不同ID"""
        repo = MetadataRepository(Path("output/json"))

        rel_id1 = repo._generate_relation_id(
            "public", "fact_sales", ["store_id"],
            "public", "dim_store", ["store_id"]
        )

        rel_id2 = repo._generate_relation_id(
            "public", "fact_sales", ["company_id"],
            "public", "dim_company", ["company_id"]
        )

        # 不同表对应生成不同ID
        assert rel_id1 != rel_id2

    def test_generate_fk_signature(self):
        """测试FK签名生成"""
        repo = MetadataRepository(Path("output/json"))

        sig = repo._generate_fk_signature(
            "public", "fact_sales", ["store_id"],
            "public", "dim_store", ["store_id"]
        )

        expected = "public.fact_sales.[store_id]->public.dim_store.[store_id]"
        assert sig == expected

    def test_generate_fk_signature_composite(self):
        """测试复合键签名生成"""
        repo = MetadataRepository(Path("output/json"))

        sig = repo._generate_fk_signature(
            "public", "fact_sales", ["store_id", "date_day"],
            "public", "dim_store", ["store_id", "date_day"]
        )

        # 列名应该被排序
        assert "date_day" in sig
        assert "store_id" in sig
        assert sig.startswith("public.fact_sales")

    def test_load_all_tables_with_real_data(self):
        """测试加载真实JSON文件"""
        json_dir = Path("output/json")

        if not json_dir.exists():
            pytest.skip("JSON目录不存在，跳过测试")

        repo = MetadataRepository(json_dir)
        tables = repo.load_all_tables()

        if not tables:
            pytest.skip("没有加载到表数据（JSON 契约已变更，需重新生成产物）")

        # 应该至少加载一些表
        assert len(tables) > 0

        # 检查表名格式
        for full_name in tables.keys():
            assert "." in full_name  # schema.table格式

    def test_load_all_tables_reads_object_info(self, tmp_path):
        """加载 JSON 时读取 object_info.object_name。"""
        (tmp_path / "orders.public.users.json").write_text(
            json.dumps(
                {
                    "metadata_version": "3.0",
                    "object_info": {
                        "schema_name": "public",
                        "object_name": "users",
                    },
                }
            ),
            encoding="utf-8",
        )
        repo = MetadataRepository(tmp_path)
        tables = repo.load_all_tables()
        assert list(tables) == ["public.users"]

        # 检查表名格式
        for full_name in tables.keys():
            assert "." in full_name  # schema.table格式

    def test_collect_foreign_keys_with_real_data(self):
        """测试外键提取（使用真实数据）"""
        json_dir = Path("output/json")

        if not json_dir.exists():
            pytest.skip("JSON目录不存在，跳过测试")

        repo = MetadataRepository(json_dir)
        tables = repo.load_all_tables()

        if not tables:
            pytest.skip("没有加载到表数据")

        fk_relations, fk_sigs = repo.collect_foreign_keys(tables)

        # FK签名集合数量应该等于关系数量
        assert len(fk_sigs) == len(fk_relations)

        # 每个关系应该有完整的字段
        for rel in fk_relations:
            assert rel.relationship_id.startswith("rel_")
            assert rel.relationship_type == "foreign_key"
            assert rel.composite_score == 1.0
            assert rel.score_details is None
            assert len(rel.source_columns) > 0
            assert len(rel.target_columns) > 0

    def test_collect_foreign_keys_assigns_fixed_score(self, tmp_path):
        """外键直通在入库时就把综合分设为 1.0，不带五维明细。"""
        repo = MetadataRepository(tmp_path)
        tables = {
            "public.screenings": {
                "object_info": {
                    "schema_name": "public",
                    "object_name": "screenings",
                },
                "table_profile": {
                    "physical_constraints": {
                        "foreign_keys": [
                            {
                                "constraint_name": "screenings_hall_id_fkey",
                                "source_columns": ["hall_id"],
                                "target_schema": "public",
                                "target_table": "cinema_halls",
                                "target_columns": ["hall_id"],
                            }
                        ]
                    }
                },
            },
            "public.cinema_halls": {
                "object_info": {
                    "schema_name": "public",
                    "object_name": "cinema_halls",
                },
                "table_profile": {"physical_constraints": {"foreign_keys": []}},
            },
        }

        fk_relations, _ = repo.collect_foreign_keys(tables)
        assert len(fk_relations) == 1
        rel = fk_relations[0]
        assert rel.source_table == "screenings"
        assert rel.target_table == "cinema_halls"
        assert rel.composite_score == 1.0
        assert rel.score_details is None
        assert rel.constraint_name == "screenings_hall_id_fkey"

    def test_compute_relationship_id_static_method(self):
        """测试静态方法 compute_relationship_id"""
        # 使用静态方法生成 ID（无盐值）
        rel_id1 = MetadataRepository.compute_relationship_id(
            "public", "fact_sales", ["store_id"],
            "public", "dim_store", ["store_id"]
        )

        # 使用静态方法生成 ID（有盐值）
        rel_id2 = MetadataRepository.compute_relationship_id(
            "public", "fact_sales", ["store_id"],
            "public", "dim_store", ["store_id"],
            rel_id_salt="myproject"
        )

        # 无盐值和有盐值应生成不同ID
        assert rel_id1 != rel_id2

        # 相同盐值应生成相同ID
        rel_id3 = MetadataRepository.compute_relationship_id(
            "public", "fact_sales", ["store_id"],
            "public", "dim_store", ["store_id"],
            rel_id_salt="myproject"
        )
        assert rel_id2 == rel_id3

    def test_compute_relationship_id_pairwise_identity(self):
        """测试按完整列对应对生成身份（2.6 升级）

        - 同一关系整体反转列对顺序应生成相同 ID；
        - 不同的字段指派（即使两侧列集合相同）应生成不同 ID。
        """
        # 顺序 A: (id, id), (code, code)
        id_a = MetadataRepository.compute_relationship_id(
            "public", "a", ["id", "code"],
            "public", "b", ["id", "code"]
        )
        # 整体反转顺序: (code, code), (id, id) —— 同一关系
        id_a_reversed_order = MetadataRepository.compute_relationship_id(
            "public", "a", ["code", "id"],
            "public", "b", ["code", "id"]
        )
        assert id_a == id_a_reversed_order

        # 不同字段指派: (id, code), (code, id) —— 不同关系
        id_b_cross = MetadataRepository.compute_relationship_id(
            "public", "a", ["id", "code"],
            "public", "b", ["code", "id"]
        )
        assert id_a != id_b_cross

    def test_compute_relationship_id_length_mismatch_raises(self):
        """测试列数不一致时抛出异常"""
        with pytest.raises(ValueError):
            MetadataRepository.compute_relationship_id(
                "public", "a", ["id", "code"],
                "public", "b", ["id"]
            )

    def test_is_columns_unique_reads_table_level_physical_constraints(self):
        """测试 _is_columns_unique 单列分支读取表级 physical_constraints（v3）"""
        repo = MetadataRepository(Path("output/json"))

        tables = {
            "public.dim_store": {
                "column_profiles": {},
                "table_profile": {
                    "physical_constraints": {
                        "primary_key": {"columns": ["store_id"]},
                        "unique_constraints": [{"columns": ["store_code"]}]
                    }
                }
            }
        }

        assert repo._is_columns_unique(tables, "public.dim_store", ["store_id"]) is True
        assert repo._is_columns_unique(tables, "public.dim_store", ["store_code"]) is True
        assert repo._is_columns_unique(tables, "public.dim_store", ["store_name"]) is False

    def test_relation_id_salt_consistency(self):
        """测试实例方法与静态方法的一致性"""
        # 创建带盐值的 repository
        repo = MetadataRepository(
            Path("output/json"),
            rel_id_salt="myproject"
        )

        # 使用实例方法生成 ID
        instance_id = repo._generate_relation_id(
            "public", "fact_sales", ["store_id"],
            "public", "dim_store", ["store_id"]
        )

        # 使用静态方法生成 ID（相同盐值）
        static_id = MetadataRepository.compute_relationship_id(
            "public", "fact_sales", ["store_id"],
            "public", "dim_store", ["store_id"],
            rel_id_salt="myproject"
        )

        # 应该生成相同的 ID
        assert instance_id == static_id


class TestDoc19Repository:
    """doc 19 §3.2.3 / §3.3 的 repository 改造测试"""

    def _repo(self, tables):
        return MetadataRepository(Path("output/json"), logical_key_min_confidence=0.8)

    def test_undirected_identity_ignores_direction(self):
        """无向身份算法(doc 19 §3.3):反向对相同、不同指派不同"""
        i1 = MetadataRepository.compute_undirected_identity(
            "s", "A", ["a", "b"], "s", "B", ["x", "y"],
        )
        i2 = MetadataRepository.compute_undirected_identity(
            "s", "B", ["y", "x"], "s", "A", ["b", "a"],
        )
        i3 = MetadataRepository.compute_undirected_identity(
            "s", "A", ["a", "b"], "s", "B", ["y", "x"],
        )
        assert i1 == i2
        assert i1 != i3

    def test_undirected_identity_casefold_then_raw_tiebreak(self):
        """比较键为 (casefold, 原始值):"Users" 与 users 仍能确定先后"""
        i1 = MetadataRepository.compute_undirected_identity(
            "s", "Users", ["id"], "s", "users", ["uid"],
        )
        i2 = MetadataRepository.compute_undirected_identity(
            "s", "users", ["uid"], "s", "Users", ["id"],
        )
        assert i1 == i2

    def test_fk_cardinality_fixed_n1_or_11(self):
        """物理 FK 基数固定(doc 19 §3.2.3):target 画像缺失不影响结果;
        source 唯一 → 1:1,否则 N:1;不得产出 1:N/M:N"""
        repo = self._repo(None)
        tables = {
            "public.orders": {
                "column_profiles": {"category_id": {"statistics": {}}},
                "table_profile": {
                    "physical_constraints": {
                        "primary_key": None,
                        "unique_constraints": [{"columns": ["category_id"]}],
                    },
                    "indexes": [],
                    "unique_column_sets": [],
                },
            },
        }
        fk = {"source_columns": ["category_id"], "target_columns": ["id"]}
        # target 表 public.categories 不在 tables 中 → 画像缺失,不影响结果
        assert repo._infer_cardinality(
            fk, tables, "public.orders", "public", "categories"
        ) == "1:1"

        fk2 = {"source_columns": ["product_id"], "target_columns": ["id"]}
        assert repo._infer_cardinality(
            fk2, tables, "public.orders", "public", "products"
        ) == "N:1"

    def test_is_columns_unique_non_partial_unique_index(self):
        """非部分/非表达式/键列完全匹配的唯一索引判定唯一(doc 19 §3.2.3)"""
        repo = self._repo(None)
        tables = {
            "public.user_profiles": {
                "column_profiles": {"user_id": {"statistics": {}}},
                "table_profile": {
                    "physical_constraints": {"primary_key": None, "unique_constraints": []},
                    "indexes": [
                        {"columns": ["user_id"], "is_unique": True, "condition": None,
                         "key_expressions": ["user_id"]},
                    ],
                    "unique_column_sets": [],
                },
            },
        }
        assert repo._is_columns_unique(tables, "public.user_profiles", ["user_id"]) is True

    def test_partial_or_expression_unique_index_not_counted(self):
        """部分唯一索引与表达式索引不算独立证据(doc 19 §3.2.3)"""
        repo = self._repo(None)
        tables = {
            "public.t": {
                "column_profiles": {"email": {"statistics": {}}},
                "table_profile": {
                    "physical_constraints": {"primary_key": None, "unique_constraints": []},
                    "indexes": [
                        {"columns": ["email"], "is_unique": True,
                         "condition": "deleted_at IS NULL", "key_expressions": ["email"]},
                        {"columns": ["email"], "is_unique": True, "condition": None,
                         "key_expressions": ["lower(email)"]},
                    ],
                    "unique_column_sets": [],
                },
            },
        }
        assert repo._is_columns_unique(tables, "public.t", ["email"]) is False

    def test_composite_uniqueness_uses_unique_column_sets_not_single_min(self):
        """复合列回退用 unique_column_sets 组合级证据(无序集合比较);
        禁止'各单列最小值'推断(doc 19 §3.2.3)"""
        repo = self._repo(None)
        tables = {
            "public.fact": {
                "column_profiles": {
                    "a": {"statistics": {"uniqueness": 0.5}},
                    "b": {"statistics": {"uniqueness": 0.5}},
                },
                "table_profile": {
                    "physical_constraints": {"primary_key": None, "unique_constraints": []},
                    "indexes": [],
                    "unique_column_sets": [
                        {"columns": ["b", "a"], "confidence_score": 0.9},
                    ],
                },
            },
        }
        # 组合唯一但各单列不唯一 → 仍判定唯一(不按单列最小值漏判)
        assert repo._is_columns_unique(tables, "public.fact", ["a", "b"]) is True
        # 无组合级证据 → 保守不唯一
        assert repo._is_columns_unique(tables, "public.fact", ["a", "c"]) is False

    def test_composite_uniqueness_respects_configured_confidence(self):
        """逻辑键置信度阈值经配置传入(doc 19 §3.2.3),不硬编码 0.8"""
        repo_high = MetadataRepository(
            Path("output/json"), logical_key_min_confidence=0.95
        )
        tables = {
            "public.fact": {
                "column_profiles": {"a": {}, "b": {}},
                "table_profile": {
                    "physical_constraints": {"primary_key": None, "unique_constraints": []},
                    "indexes": [],
                    "unique_column_sets": [
                        {"columns": ["a", "b"], "confidence_score": 0.9},
                    ],
                },
            },
        }
        assert repo_high._is_columns_unique(tables, "public.fact", ["a", "b"]) is False

    def test_fk_kept_when_source_statistics_null_or_missing(self):
        """源字段 statistics 缺失或为 null 时,FK 必须保留且保守 N:1
        (doc 19 §3.2.3:画像缺失时保守视为不唯一,不得抛异常丢 FK)"""
        repo = self._repo(None)
        tables = {
            "public.orders": {
                "column_profiles": {"category_id": {"statistics": None}},
                "table_profile": {
                    "physical_constraints": {"primary_key": None, "unique_constraints": []},
                    "indexes": [],
                    "unique_column_sets": [],
                },
            },
            "public.orders_no_stats": {
                "column_profiles": {"category_id": {}},
                "table_profile": {
                    "physical_constraints": {"primary_key": None, "unique_constraints": []},
                    "indexes": [],
                    "unique_column_sets": [],
                },
            },
        }
        fk = {"source_columns": ["category_id"], "target_columns": ["id"]}
        assert repo._infer_cardinality(
            fk, tables, "public.orders", "public", "categories"
        ) == "N:1"
        assert repo._infer_cardinality(
            fk, tables, "public.orders_no_stats", "public", "categories"
        ) == "N:1"
