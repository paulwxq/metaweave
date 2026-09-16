"""测试 CandidateGenerator（doc 15 统一改造版）

覆盖 docs/update/15_rel与rel_llm候选生成统一改造设计.md §8.1~§8.4 的核心用例：
- 源侧键集统一收集（单列/复合、物理/逻辑）
- 目标列池构建（metric/complex 剔除）
- 递进闸门（名称 embedding OR 注释 embedding，短路语义）
- 集合指派（非贪心，假阴性回归）
- 合并去重（池内统一去重、最小键过滤、来源合并、FK 排除）
- LLM 候选入池（合法性过滤 + top-K 截断）
"""

import pytest

from metaweave.core.relationships.candidate_generator import CandidateGenerator


class FakeNameSimilarityService:
    """可控的名称/注释相似度服务替身，用于确定性测试闸门逻辑"""

    def __init__(self, name_sim=None, comment_sim=None):
        # {(a_lower, b_lower): score}
        self.name_sim = name_sim or {}
        # {(a, b): score or None}
        self.comment_sim = comment_sim or {}
        self.name_calls = []

    def compare_pair(self, a: str, b: str) -> float:
        self.name_calls.append((a, b))
        an, bn = a.strip().lower(), b.strip().lower()
        if an == bn:
            return 1.0
        return self.name_sim.get((an, bn), 0.0)

    def compare_columns(self, source_cols, target_cols):
        if len(source_cols) != len(target_cols):
            return 0.0
        return sum(self.compare_pair(a, b) for a, b in zip(source_cols, target_cols)) / len(source_cols)

    def compare_comment_pair(self, a, b):
        if a is None or b is None:
            return None
        return self.comment_sim.get((a, b))


def _candidate_matching_config(**overrides):
    cfg = {
        "candidate_matching": {
            "max_columns": 3,
            "name_threshold": 0.9,
            "comment_threshold": 0.85,
            "type_threshold": 0.8,
            "logical_key_min_confidence": 0.8,
            "exclude_target_semantic_roles": ["metric"],
            "exclude_target_complex_types": True,
        }
    }
    cfg["candidate_matching"].update(overrides)
    return cfg


def _table(schema, table, columns, table_profile=None):
    return {
        "table_info": {"schema_name": schema, "table_name": table},
        "column_profiles": columns,
        "table_profile": table_profile or {},
    }


class TestSourceKeySetCollection:
    """§8.1：源侧统一收集测试"""

    def test_single_column_physical_pk_enters_source_key_sets(self):
        generator = CandidateGenerator(_candidate_matching_config())
        table = _table(
            "public", "dim_store", {"store_id": {"data_type": "integer"}},
            table_profile={
                "physical_constraints": {
                    "primary_key": {"columns": ["store_id"]},
                    "unique_constraints": [],
                }
            },
        )
        key_sets = generator._collect_source_key_sets(table)
        assert {"columns": ["store_id"], "origin": "physical"} in key_sets

    def test_single_column_unique_constraint_enters_source_key_sets(self):
        generator = CandidateGenerator(_candidate_matching_config())
        table = _table(
            "public", "dim_store", {"store_code": {"data_type": "varchar"}},
            table_profile={
                "physical_constraints": {
                    "primary_key": None,
                    "unique_constraints": [{"columns": ["store_code"]}],
                }
            },
        )
        key_sets = generator._collect_source_key_sets(table)
        assert {"columns": ["store_code"], "origin": "physical"} in key_sets

    def test_single_column_logical_key_enters_source_key_sets(self):
        generator = CandidateGenerator(_candidate_matching_config())
        table = _table(
            "public", "dim_store", {"external_code": {"data_type": "varchar"}},
            table_profile={
                "physical_constraints": {"primary_key": None, "unique_constraints": []},
                "unique_column_sets": [
                    {"columns": ["external_code"], "confidence_score": 0.9}
                ],
            },
        )
        key_sets = generator._collect_source_key_sets(table)
        assert {"columns": ["external_code"], "origin": "logical"} in key_sets

    def test_logical_key_below_min_confidence_excluded(self):
        generator = CandidateGenerator(_candidate_matching_config())
        table = _table(
            "public", "dim_store", {"maybe_code": {"data_type": "varchar"}},
            table_profile={
                "physical_constraints": {"primary_key": None, "unique_constraints": []},
                "unique_column_sets": [
                    {"columns": ["maybe_code"], "confidence_score": 0.5}
                ],
            },
        )
        key_sets = generator._collect_source_key_sets(table)
        assert key_sets == []

    def test_composite_physical_key_and_single_key_share_same_matcher(self):
        """N 列复合键与单列键走同一收集器，不再分流"""
        generator = CandidateGenerator(_candidate_matching_config())
        table = _table(
            "public", "fact_sales",
            {"store_id": {"data_type": "integer"}, "date_day": {"data_type": "date"}},
            table_profile={
                "physical_constraints": {
                    "primary_key": {"columns": ["store_id", "date_day"]},
                    "unique_constraints": [],
                }
            },
        )
        key_sets = generator._collect_source_key_sets(table)
        assert {"columns": ["store_id", "date_day"], "origin": "physical"} in key_sets

    def test_key_set_wider_than_max_columns_excluded(self):
        generator = CandidateGenerator(_candidate_matching_config(max_columns=3))
        table = _table(
            "public", "fact_sales",
            {c: {"data_type": "integer"} for c in ["a", "b", "c", "d"]},
            table_profile={
                "physical_constraints": {
                    "primary_key": {"columns": ["a", "b", "c", "d"]},
                    "unique_constraints": [],
                }
            },
        )
        key_sets = generator._collect_source_key_sets(table)
        assert key_sets == []

    def test_reversed_order_pk_and_uk_are_not_merged(self):
        """PK(a,b) 与 UK(b,a) 列顺序不同，属于两个独立声明键，不应被去重合并
        （doc 15 §3.8：列对应顺序是身份的一部分）"""
        generator = CandidateGenerator(_candidate_matching_config())
        table = _table(
            "public", "fact_sales",
            {"a": {"data_type": "integer"}, "b": {"data_type": "integer"}},
            table_profile={
                "physical_constraints": {
                    "primary_key": {"columns": ["a", "b"]},
                    "unique_constraints": [{"columns": ["b", "a"]}],
                }
            },
        )
        key_sets = generator._collect_source_key_sets(table)
        assert {"columns": ["a", "b"], "origin": "physical"} in key_sets
        assert {"columns": ["b", "a"], "origin": "physical"} in key_sets
        assert len(key_sets) == 2

    def test_same_order_duplicate_declaration_still_deduped(self):
        """同一列顺序重复声明（如相同列的 PK 与冗余 UK）仍应去重为一个键集"""
        generator = CandidateGenerator(_candidate_matching_config())
        table = _table(
            "public", "fact_sales",
            {"a": {"data_type": "integer"}, "b": {"data_type": "integer"}},
            table_profile={
                "physical_constraints": {
                    "primary_key": {"columns": ["a", "b"]},
                    "unique_constraints": [{"columns": ["a", "b"]}],
                }
            },
        )
        key_sets = generator._collect_source_key_sets(table)
        assert key_sets == [{"columns": ["a", "b"], "origin": "physical"}]


class TestTargetColumnPool:
    """§3.3：目标列池构建（角色过滤前置）"""

    def test_metric_role_excluded_from_pool(self):
        generator = CandidateGenerator(_candidate_matching_config())
        table = _table("public", "fact_sales", {
            "amount": {"data_type": "numeric", "semantic_analysis": {"semantic_role": "metric"}},
            "store_id": {"data_type": "integer", "semantic_analysis": {"semantic_role": "identifier"}},
        })
        pool = generator._build_target_column_pool(table)
        assert "amount" not in pool
        assert "store_id" in pool

    def test_complex_type_excluded_from_pool(self):
        generator = CandidateGenerator(_candidate_matching_config())
        table = _table("public", "fact_sales", {
            "payload": {"data_type": "jsonb"},
            "store_id": {"data_type": "integer"},
        })
        pool = generator._build_target_column_pool(table)
        assert "payload" not in pool
        assert "store_id" in pool

    def test_pk_uk_index_audit_description_all_treated_equally(self):
        """目标侧不再对 PK/UK/索引/audit/description 做特权处理，只剔除 metric/complex"""
        generator = CandidateGenerator(_candidate_matching_config())
        table = _table("public", "dim_store", {
            "store_id": {"data_type": "integer"},  # 假设的物理 PK，不特殊处理
            "created_at": {"data_type": "timestamp", "semantic_analysis": {"semantic_role": "audit"}},
            "description": {"data_type": "text", "semantic_analysis": {"semantic_role": "description"}},
        })
        pool = generator._build_target_column_pool(table)
        assert set(pool) == {"store_id", "created_at", "description"}


class TestProgressiveGate:
    """§8.2：闸门组合测试"""

    def test_same_name_case_insensitive_short_circuits_without_api(self):
        fake = FakeNameSimilarityService()
        generator = CandidateGenerator(_candidate_matching_config(), fake)
        assert generator._passes_gate("Store_ID", None, "store_id", None) is True
        # 同名短路：compare_pair 内部按 normalize 后判等，不查表就是 1.0，无需 mock 断言调用次数
        assert fake.name_sim == {}

    def test_low_name_high_comment_passes(self):
        fake = FakeNameSimilarityService(
            name_sim={("region_id", "area_id"): 0.5},
            comment_sim={("区域编号", "所属地区编号"): 0.9},
        )
        generator = CandidateGenerator(_candidate_matching_config(), fake)
        assert generator._passes_gate("region_id", "区域编号", "area_id", "所属地区编号") is True

    def test_low_name_empty_comment_rejected(self):
        fake = FakeNameSimilarityService(name_sim={("region_id", "area_id"): 0.5})
        generator = CandidateGenerator(_candidate_matching_config(), fake)
        assert generator._passes_gate("region_id", None, "area_id", None) is False

    def test_low_name_generic_comment_rejected(self):
        """通用注释黑名单命中 → comment_channel.compare 返回 None（由服务自身黑名单逻辑负责，
        此处用 FakeNameSimilarityService 模拟"注释不可用"的返回值 None）"""
        fake = FakeNameSimilarityService(
            name_sim={("id", "id2"): 0.3},
            comment_sim={},  # 黑名单词不在字典中 -> compare_comment_pair 返回 None
        )
        generator = CandidateGenerator(_candidate_matching_config(), fake)
        assert generator._passes_gate("id", "编号", "id2", "编号") is False

    def test_gate_passed_but_type_incompatible_rejected(self):
        fake = FakeNameSimilarityService()
        generator = CandidateGenerator(_candidate_matching_config())
        source_profile = {"data_type": "integer", "comment": None}
        target_profiles = {"amount": {"data_type": "text", "comment": None}}
        qualifying = generator._qualifying_targets(
            "amount", source_profile, ["amount"], target_profiles
        )
        assert qualifying == set()

    def test_degraded_mode_without_service_falls_back_to_exact_name(self):
        """无 embedding 环境降级语义：名称闸退化为同名短路"""
        generator = CandidateGenerator(_candidate_matching_config(), name_similarity_service=None)
        assert generator._passes_gate("store_id", None, "store_id", None) is True
        assert generator._passes_gate("store_id", None, "other_id", None) is False


class TestSetAssignment:
    """§8.3：集合指派测试（假阴性回归）"""

    def test_non_greedy_assignment_finds_valid_permutation(self):
        """col1 候选 {X, Y}，col2 候选 {X}：必须找到 col1->Y, col2->X"""
        qualifying_sets = [{"X", "Y"}, {"X"}]
        assignments = CandidateGenerator._find_all_assignments(qualifying_sets)
        assert ["Y", "X"] in assignments

    def test_empty_candidate_set_aborts_combination(self):
        qualifying_sets = [{"X"}, set()]
        assignments = CandidateGenerator._find_all_assignments(qualifying_sets)
        assert assignments == []

    def test_no_duplicate_target_column_in_assignment(self):
        qualifying_sets = [{"X", "Y"}, {"X", "Y"}]
        assignments = CandidateGenerator._find_all_assignments(qualifying_sets)
        for assignment in assignments:
            assert len(set(assignment)) == len(assignment)

    def test_ascending_pruning_preserves_result_set_and_original_column_order(self):
        """doc 15 §3.6 末段：源列按候选集大小升序回溯是纯性能优化，
        结果集合（含每个 assignment 内的原始源列顺序）必须与未优化前完全一致。
        构造候选集大小差异明显的 3 列键（大候选集在前，小候选集在后），
        验证排序+还原逻辑不会打乱 assignment 与原始源列的对应关系。
        """
        # 源列顺序：col0(大候选集) -> col1(中候选集) -> col2(小候选集，仅1个候选)
        qualifying_sets = [
            {"A", "B", "C"},  # col0：大候选集，排序后应最后处理
            {"A", "B"},       # col1：中候选集
            {"C"},            # col2：小候选集，排序后应最先处理
        ]
        assignments = CandidateGenerator._find_all_assignments(qualifying_sets)

        # 手工枚举期望结果（保持 col0/col1/col2 的原始位置语义）：
        # col2 只能取 C；剩下 col0/col1 从 {A, B} 中互不重复地各取一个
        expected = [["A", "B", "C"], ["B", "A", "C"]]
        assert sorted(assignments) == sorted(expected)

        # 每个 assignment 的第 2 位（col2）必须始终是 "C"，证明还原未错位
        for assignment in assignments:
            assert assignment[2] == "C"

    def test_assignment_count_debug_log_reports_scale(self, caplog):
        """doc 15 §3.6 建议：debug 日志报告单键集的指派数，便于观察实际规模"""
        import logging as logging_module

        qualifying_sets = [{"X", "Y"}, {"X", "Y"}]
        with caplog.at_level(logging_module.DEBUG, logger="metaweave.relationships.candidate_generator"):
            assignments = CandidateGenerator._find_all_assignments(qualifying_sets)

        assert any("指派数" in record.message for record in caplog.records)
        assert any(str(len(assignments)) in record.message for record in caplog.records)


class TestGenerateCandidatesRulePath:
    """规则候选生成主流程（单列 + 复合共用同一管线，doc 19 方向规范化）"""

    def test_single_column_physical_key_candidate_generated(self):
        """规则候选生成时即规范化方向（关联字段表 → 键表，doc 19 §3.2.1）"""
        fake = FakeNameSimilarityService()
        generator = CandidateGenerator(_candidate_matching_config(), fake)

        tables = {
            "public.fact_sales": _table(
                "public", "fact_sales", {"store_id": {"data_type": "integer"}},
                table_profile={
                    "physical_constraints": {
                        "primary_key": {"columns": ["store_id"]},
                        "unique_constraints": [],
                    }
                },
            ),
            "public.dim_store": _table(
                "public", "dim_store", {"store_id": {"data_type": "integer"}}
            ),
        }
        rule_pool, llm_pool = generator.generate_candidates(
            tables, [("public.fact_sales", "public.dim_store")], set()
        )
        assert llm_pool == []
        matches = [
            c for c in rule_pool
            if c["source_columns"] == ["store_id"] and c["target_columns"] == ["store_id"]
            and c["candidate_origin"] == "rule" and c["key_origin"] == "physical"
        ]
        assert len(matches) == 1
        # 方向规范化：关联字段表（dim_store）为 source，键表（fact_sales）为 target
        assert matches[0]["source"]["table_info"]["table_name"] == "dim_store"
        assert matches[0]["target"]["table_info"]["table_name"] == "fact_sales"

    def test_composite_key_candidate_generated(self):
        fake = FakeNameSimilarityService()
        generator = CandidateGenerator(_candidate_matching_config(), fake)

        tables = {
            "public.fact_sales": _table(
                "public", "fact_sales",
                {"store_id": {"data_type": "integer"}, "date_day": {"data_type": "date"}},
                table_profile={
                    "physical_constraints": {
                        "primary_key": {"columns": ["store_id", "date_day"]},
                        "unique_constraints": [],
                    }
                },
            ),
            "public.dim_store_calendar": _table(
                "public", "dim_store_calendar",
                {"store_id": {"data_type": "integer"}, "date_day": {"data_type": "date"}},
            ),
        }
        rule_pool, _ = generator.generate_candidates(
            tables, [("public.fact_sales", "public.dim_store_calendar")], set()
        )
        composite = [c for c in rule_pool if len(c["source_columns"]) == 2]
        assert len(composite) == 1
        # 键列在 target（键表侧），关联列在 source（关联字段表侧）
        assert composite[0]["source"]["table_info"]["table_name"] == "dim_store_calendar"
        assert composite[0]["target"]["table_info"]["table_name"] == "fact_sales"
        assert set(composite[0]["target_columns"]) == {"store_id", "date_day"}

    def test_target_metric_column_never_becomes_candidate(self):
        fake = FakeNameSimilarityService()
        generator = CandidateGenerator(_candidate_matching_config(), fake)

        tables = {
            "public.fact_sales": _table(
                "public", "fact_sales", {"amount": {"data_type": "numeric"}},
                table_profile={
                    "physical_constraints": {
                        "primary_key": {"columns": ["amount"]},
                        "unique_constraints": [],
                    }
                },
            ),
            "public.dim_amount": _table(
                "public", "dim_amount",
                {"amount": {"data_type": "numeric", "semantic_analysis": {"semantic_role": "metric"}}},
            ),
        }
        rule_pool, llm_pool = generator.generate_candidates(
            tables, [("public.fact_sales", "public.dim_amount")], set()
        )
        assert rule_pool == []
        assert llm_pool == []


class TestMergeDedupAndFKExclusion:
    """doc 19 §3.1：分池出口（同向去重 + 最小键过滤 + FK 排除，评分前）"""

    def _two_table_setup(self):
        fake = FakeNameSimilarityService()
        generator = CandidateGenerator(_candidate_matching_config(), fake)
        tables = {
            "public.fact_sales": _table(
                "public", "fact_sales", {"store_id": {"data_type": "integer"}},
                table_profile={
                    "physical_constraints": {
                        "primary_key": {"columns": ["store_id"]},
                        "unique_constraints": [],
                    }
                },
            ),
            "public.dim_store": _table(
                "public", "dim_store", {"store_id": {"data_type": "integer"}}
            ),
        }
        return generator, tables

    def test_candidate_matching_existing_fk_excluded(self):
        """FK 排除保留在规则池评分前（双向检查，见 doc 19 §3.1）"""
        from metaweave.core.relationships.repository import MetadataRepository

        generator, tables = self._two_table_setup()
        # 规范化方向（dim_store -> fact_sales）与反向 FK 身份都应能排除候选
        fwd_fk_id = MetadataRepository.compute_relationship_id(
            "public", "dim_store", ["store_id"],
            "public", "fact_sales", ["store_id"],
            rel_id_salt="",
        )
        rev_fk_id = MetadataRepository.compute_relationship_id(
            "public", "fact_sales", ["store_id"],
            "public", "dim_store", ["store_id"],
            rel_id_salt="",
        )
        rule_pool, _ = generator.generate_candidates(
            tables, [("public.fact_sales", "public.dim_store")], {fwd_fk_id}
        )
        assert rule_pool == []
        rule_pool_rev, _ = generator.generate_candidates(
            tables, [("public.fact_sales", "public.dim_store")], {rev_fk_id}
        )
        assert rule_pool_rev == []

    def test_rule_and_llm_pools_kept_separate(self):
        """跨来源合并不再发生在生成阶段（doc 19 §3.1：挪到评分后合并阶段）"""
        generator, tables = self._two_table_setup()
        llm_raw = [{
            "type": "single_column",
            "from_table": {"schema": "public", "table": "dim_store"},
            "from_column": "store_id",
            "to_table": {"schema": "public", "table": "fact_sales"},
            "to_column": "store_id",
            "confidence": 0.7,
        }]
        rule_pool, llm_pool = generator.generate_candidates(
            tables, [("public.fact_sales", "public.dim_store")], set(),
            llm_raw_candidates=llm_raw,
        )
        assert len(rule_pool) == 1
        assert rule_pool[0]["candidate_origin"] == "rule"
        assert len(llm_pool) == 1
        assert llm_pool[0]["candidate_origin"] == "llm"

    def test_llm_only_candidate_kept_with_llm_origin(self):
        fake = FakeNameSimilarityService()
        generator = CandidateGenerator(_candidate_matching_config(), fake)
        tables = {
            "public.orders": _table("public", "orders", {"region_code": {"data_type": "varchar"}}),
            "public.regions": _table("public", "regions", {"area_code": {"data_type": "varchar"}}),
        }
        llm_raw = [{
            "type": "single_column",
            "from_table": {"schema": "public", "table": "orders"},
            "from_column": "region_code",
            "to_table": {"schema": "public", "table": "regions"},
            "to_column": "area_code",
            "confidence": 0.8,
        }]
        rule_pool, llm_pool = generator.generate_candidates(
            tables, [("public.orders", "public.regions")], set(),
            llm_raw_candidates=llm_raw,
        )
        assert rule_pool == []
        assert len(llm_pool) == 1
        assert llm_pool[0]["candidate_origin"] == "llm"

    def test_llm_candidate_targeting_metric_column_dropped(self):
        generator, tables = self._two_table_setup()
        tables["public.dim_store"]["column_profiles"]["store_id"]["semantic_analysis"] = {
            "semantic_role": "metric"
        }
        llm_raw = [{
            "type": "single_column",
            "from_table": {"schema": "public", "table": "fact_sales"},
            "from_column": "store_id",
            "to_table": {"schema": "public", "table": "dim_store"},
            "to_column": "store_id",
            "confidence": 0.9,
        }]
        _, llm_pool = generator.generate_candidates(
            tables, [("public.fact_sales", "public.dim_store")], set(),
            llm_raw_candidates=llm_raw,
        )
        assert llm_pool == []

    def test_llm_candidate_with_ghost_source_column_dropped(self):
        """LLM 编造的源列不在源表 column_profiles 中时，入池前丢弃，避免评分阶段对幽灵列发 SQL"""
        generator, tables = self._two_table_setup()
        llm_raw = [{
            "type": "single_column",
            "from_table": {"schema": "public", "table": "dim_store"},
            "from_column": "not_a_real_column",
            "to_table": {"schema": "public", "table": "fact_sales"},
            "to_column": "store_id",
            "confidence": 0.9,
        }]
        _, llm_pool = generator.generate_candidates(
            tables, [("public.fact_sales", "public.dim_store")], set(),
            llm_raw_candidates=llm_raw,
        )
        for c in llm_pool:
            assert "not_a_real_column" not in c["source_columns"]

    def test_llm_candidates_truncated_by_top_k_confidence_desc(self):
        """LLM 候选按 confidence 降序全局截断，只保留前 top_k 个"""
        fake = FakeNameSimilarityService()
        generator = CandidateGenerator(_candidate_matching_config(), fake)
        tables = {
            "public.orders": _table(
                "public", "orders",
                {"region_code": {"data_type": "varchar"}, "cust_code": {"data_type": "varchar"}},
            ),
            "public.regions": _table(
                "public", "regions",
                {"area_code": {"data_type": "varchar"}, "code": {"data_type": "varchar"}},
            ),
        }
        llm_raw = [
            {
                "type": "single_column",
                "from_table": {"schema": "public", "table": "orders"},
                "from_column": "region_code",
                "to_table": {"schema": "public", "table": "regions"},
                "to_column": "area_code",
                "confidence": 0.3,
            },
            {
                "type": "single_column",
                "from_table": {"schema": "public", "table": "orders"},
                "from_column": "cust_code",
                "to_table": {"schema": "public", "table": "regions"},
                "to_column": "code",
                "confidence": 0.9,
            },
        ]
        _, llm_pool = generator.generate_candidates(
            tables, [("public.orders", "public.regions")], set(),
            llm_raw_candidates=llm_raw, llm_top_k=1,
        )
        assert len(llm_pool) == 1
        assert llm_pool[0]["source_columns"] == ["cust_code"]
        assert llm_pool[0]["target_columns"] == ["code"]
        assert llm_pool[0]["candidate_origin"] == "llm"

    def test_truncate_llm_top_k_rejects_non_positive(self):
        with pytest.raises(ValueError, match="正整数"):
            CandidateGenerator._truncate_llm_top_k([{}], 0)
        with pytest.raises(ValueError, match="正整数"):
            CandidateGenerator._truncate_llm_top_k([{}], -1)

    def test_superkey_composite_dropped_when_single_key_exists(self):
        """最小键过滤：单列键已成立时，复合 superkey 候选被丢弃（规则池内自过滤）"""
        fake = FakeNameSimilarityService()
        generator = CandidateGenerator(_candidate_matching_config(), fake)

        tables = {
            "public.fact_sales": _table(
                "public", "fact_sales",
                {"id": {"data_type": "integer"}, "tenant_id": {"data_type": "integer"}},
                table_profile={
                    "physical_constraints": {
                        "primary_key": {"columns": ["id"]},
                        "unique_constraints": [{"columns": ["id", "tenant_id"]}],
                    }
                },
            ),
            "public.dim_target": _table(
                "public", "dim_target",
                {"id": {"data_type": "integer"}, "tenant_id": {"data_type": "integer"}},
            ),
        }
        rule_pool, _ = generator.generate_candidates(
            tables, [("public.fact_sales", "public.dim_target")], set()
        )
        # 只应保留单列候选（规范化后 dim_target.id -> fact_sales.id），
        # 复合 (id, tenant_id) 候选作为 superkey 被丢弃
        assert len(rule_pool) == 1
        assert rule_pool[0]["source_columns"] == ["id"]
        assert rule_pool[0]["source"]["table_info"]["table_name"] == "dim_target"
        assert rule_pool[0]["target"]["table_info"]["table_name"] == "fact_sales"

    def test_reversed_column_pair_order_merges_to_same_relationship(self):
        """(A.id->B.id, A.code->B.code) 与 (A.code->B.code, A.id->B.id) 应合并为同一关系"""
        generator, _ = self._two_table_setup()

        table_a = _table("public", "t_a", {
            "id": {"data_type": "integer"}, "code": {"data_type": "varchar"},
        })
        table_b = _table("public", "t_b", {
            "id": {"data_type": "integer"}, "code": {"data_type": "varchar"},
        })

        candidate_1 = {
            "source": table_a, "target": table_b,
            "source_columns": ["id", "code"], "target_columns": ["id", "code"],
            "candidate_origin": "rule", "key_origin": "physical",
        }
        candidate_2 = {
            "source": table_a, "target": table_b,
            "source_columns": ["code", "id"], "target_columns": ["code", "id"],
            "candidate_origin": "rule", "key_origin": "physical",
        }
        deduped = generator._dedup_rule_pool([candidate_1, candidate_2])
        assert len(deduped) == 1

    def test_different_field_assignment_not_merged(self):
        """(A.id->B.id, A.code->B.code) 与 (A.id->B.code, A.code->B.id) 是不同关系"""
        generator, _ = self._two_table_setup()

        table_a = _table("public", "t_a", {
            "id": {"data_type": "integer"}, "code": {"data_type": "varchar"},
        })
        table_b = _table("public", "t_b", {
            "id": {"data_type": "integer"}, "code": {"data_type": "varchar"},
        })

        candidate_1 = {
            "source": table_a, "target": table_b,
            "source_columns": ["id", "code"], "target_columns": ["id", "code"],
            "candidate_origin": "rule", "key_origin": "physical",
        }
        candidate_2 = {
            "source": table_a, "target": table_b,
            "source_columns": ["id", "code"], "target_columns": ["code", "id"],
            "candidate_origin": "rule", "key_origin": "physical",
        }
        deduped = generator._dedup_rule_pool([candidate_1, candidate_2])
        assert len(deduped) == 2

    def test_rule_pool_key_origin_physical_preferred_over_logical(self):
        """规则池同向去重:key_origin 按 physical > logical 保留,与遍历顺序无关
        (doc 19 §3.1.1)"""
        generator, _ = self._two_table_setup()

        table_a = _table("public", "t_a", {"id": {"data_type": "integer"}})
        table_b = _table("public", "t_b", {"id": {"data_type": "integer"}})

        logical_first = {
            "source": table_a, "target": table_b,
            "source_columns": ["id"], "target_columns": ["id"],
            "candidate_origin": "rule", "key_origin": "logical",
        }
        physical_second = {
            "source": table_a, "target": table_b,
            "source_columns": ["id"], "target_columns": ["id"],
            "candidate_origin": "rule", "key_origin": "physical",
        }
        deduped = generator._dedup_rule_pool([logical_first, physical_second])
        assert len(deduped) == 1
        assert deduped[0]["key_origin"] == "physical"

        deduped_rev = generator._dedup_rule_pool([physical_second, logical_first])
        assert len(deduped_rev) == 1
        assert deduped_rev[0]["key_origin"] == "physical"

    def test_llm_dedup_before_top_k(self):
        """LLM 去重先于 top_k(doc 19 §3.1.1):top_k=2 下 A(0.9)/A(0.8)/B(0.7)
        截断结果为 A、B,重复 A 不占名额"""
        fake = FakeNameSimilarityService()
        generator = CandidateGenerator(_candidate_matching_config(), fake)
        tables = {
            "public.orders": _table("public", "orders", {"code": {"data_type": "varchar"}}),
            "public.regions": _table("public", "regions", {"code": {"data_type": "varchar"}}),
        }
        llm_raw = [
            {"type": "single_column", "from_table": {"schema": "public", "table": "orders"},
             "from_column": "code", "to_table": {"schema": "public", "table": "regions"},
             "to_column": "code", "confidence": 0.9},
            {"type": "single_column", "from_table": {"schema": "public", "table": "orders"},
             "from_column": "code", "to_table": {"schema": "public", "table": "regions"},
             "to_column": "code", "confidence": 0.8},
        ]
        _, llm_pool = generator.generate_candidates(
            tables, [("public.orders", "public.regions")], set(),
            llm_raw_candidates=llm_raw, llm_top_k=2,
        )
        assert len(llm_pool) == 1  # 去重后只剩 A

        # A/A/B 场景:B 不得被重复 A 挤出 top_k
        llm_raw_with_b = llm_raw + [
            {"type": "single_column", "from_table": {"schema": "public", "table": "orders"},
             "from_column": "code2", "to_table": {"schema": "public", "table": "regions"},
             "to_column": "code2", "confidence": 0.7},
        ]
        tables["public.orders"]["column_profiles"]["code2"] = {"data_type": "varchar"}
        tables["public.regions"]["column_profiles"]["code2"] = {"data_type": "varchar"}
        _, llm_pool2 = generator.generate_candidates(
            tables, [("public.orders", "public.regions")], set(),
            llm_raw_candidates=llm_raw_with_b, llm_top_k=2,
        )
        assert len(llm_pool2) == 2
        assert {c["source_columns"][0] for c in llm_pool2} == {"code", "code2"}

    def test_llm_top_k_tie_order_and_salt_independent(self):
        """top_k 并列按未加盐规范身份升序:与输入顺序、rel_id_salt 无关
        (doc 19 §3.1.1)"""
        fake = FakeNameSimilarityService()
        tables = {
            "public.orders": _table(
                "public", "orders",
                {"alpha": {"data_type": "varchar"}, "beta": {"data_type": "varchar"}},
            ),
            "public.regions": _table(
                "public", "regions",
                {"x": {"data_type": "varchar"}, "y": {"data_type": "varchar"}},
            ),
        }

        def make_raw():
            return [
                {"type": "single_column",
                 "from_table": {"schema": "public", "table": "orders"},
                 "from_column": "alpha", "to_table": {"schema": "public", "table": "regions"},
                 "to_column": "x", "confidence": 0.5},
                {"type": "single_column",
                 "from_table": {"schema": "public", "table": "orders"},
                 "from_column": "beta", "to_table": {"schema": "public", "table": "regions"},
                 "to_column": "y", "confidence": 0.5},
            ]

        gen1 = CandidateGenerator(_candidate_matching_config(), fake, rel_id_salt="salt-a")
        gen2 = CandidateGenerator(_candidate_matching_config(), fake, rel_id_salt="salt-b")
        _, pool1 = gen1.generate_candidates(
            tables, [("public.orders", "public.regions")], set(),
            llm_raw_candidates=make_raw(), llm_top_k=1,
        )
        _, pool2 = gen2.generate_candidates(
            tables, [("public.orders", "public.regions")], set(),
            llm_raw_candidates=list(reversed(make_raw())), llm_top_k=1,
        )
        assert pool1[0]["source_columns"] == pool2[0]["source_columns"]
        # 并列时按签名升序:alpha=x 签名 < beta=y 签名
        assert pool1[0]["source_columns"] == ["alpha"]

    def test_rule_single_suppresses_llm_composite_only(self):
        """最小键过滤单向(doc 19 §3.1.1):规则单列抑制 LLM 复合;
        LLM 单列不抑制规则复合(规则池先行自过滤)"""
        fake = FakeNameSimilarityService()
        generator = CandidateGenerator(_candidate_matching_config(), fake)
        tables = {
            "public.fact": _table(
                "public", "fact",
                {"id": {"data_type": "integer"}, "tenant_id": {"data_type": "integer"}},
                table_profile={
                    "physical_constraints": {
                        "primary_key": {"columns": ["id"]},
                        "unique_constraints": [{"columns": ["id", "tenant_id"]}],
                    }
                },
            ),
            "public.dim": _table(
                "public", "dim",
                {"id": {"data_type": "integer"}, "tenant_id": {"data_type": "integer"}},
            ),
        }
        llm_raw = [
            {"type": "composite",
             "from_table": {"schema": "public", "table": "dim"},
             "from_columns": ["id", "tenant_id"],
             "to_table": {"schema": "public", "table": "fact"},
             "to_columns": ["id", "tenant_id"],
             "confidence": 0.9},
            {"type": "single_column",
             "from_table": {"schema": "public", "table": "dim"},
             "from_column": "id",
             "to_table": {"schema": "public", "table": "fact"},
             "to_column": "id",
             "confidence": 0.8},
        ]
        rule_pool, llm_pool = generator.generate_candidates(
            tables, [("public.fact", "public.dim")], set(),
            llm_raw_candidates=llm_raw,
        )
        # 规则池:单列保留,复合 superkey 被池内自过滤
        assert len(rule_pool) == 1
        assert rule_pool[0]["source_columns"] == ["id"]
        # LLM 池:复合 superkey 于"规则单列 ∪ LLM 单列"→ 被丢弃;单列保留
        assert len(llm_pool) == 1
        assert llm_pool[0]["source_columns"] == ["id"]

    def test_llm_single_does_not_suppress_rule_composite(self):
        """LLM 单列不抑制规则复合(doc 19 §3.1.1:单向抑制)"""
        fake = FakeNameSimilarityService()
        generator = CandidateGenerator(_candidate_matching_config(), fake)
        tables = {
            "public.fact": _table(
                "public", "fact",
                {"id": {"data_type": "integer"}, "tenant_id": {"data_type": "integer"}},
                table_profile={
                    "physical_constraints": {
                        "primary_key": {"columns": ["id", "tenant_id"]},
                        "unique_constraints": [],
                    }
                },
            ),
            "public.dim": _table(
                "public", "dim",
                {"id": {"data_type": "integer"}, "tenant_id": {"data_type": "integer"}},
            ),
        }
        llm_raw = [{
            "type": "single_column",
            "from_table": {"schema": "public", "table": "dim"},
            "from_column": "id",
            "to_table": {"schema": "public", "table": "fact"},
            "to_column": "id",
            "confidence": 0.9,
        }]
        rule_pool, llm_pool = generator.generate_candidates(
            tables, [("public.fact", "public.dim")], set(),
            llm_raw_candidates=llm_raw,
        )
        # 规则池只有复合键(无单列键),复合候选保留——不被 LLM 单列抑制
        assert len(rule_pool) == 1
        assert rule_pool[0]["source_columns"] == ["id", "tenant_id"]
        assert len(llm_pool) == 1
