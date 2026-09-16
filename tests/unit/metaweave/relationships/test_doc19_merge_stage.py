"""doc 19 合并阶段（七步）单元测试

覆盖 docs/update/19_rel方向统一与评分后合并设计.md §5 的核心用例：
- ① 评分后纠偏（按来源：LLM 判反 / 物理键约束修正 / 逻辑键失效丢弃）
- ② 无向身份分组（不依赖方向，反向案例合并）
- ③ 组内 cardinality 决策（双向物理/逻辑 → 1:1；键证据优先级）
- ④ 按最终 cardinality 决定唯一方向（N:1 键证据方向 / 1:1 层级 / M:N 字典序）
- ⑤ 规范到最终方向 + 重算（reverse_inclusion_rate、composite 同步）
- ⑥ 字段级合并（候选决胜键、key_origin 不与方向脱节）
- ⑦ 生成最终有向 relationship_id
"""

from types import SimpleNamespace

from metaweave.core.relationships.pipeline import RelationshipDiscoveryPipeline

FIVE_DIM_WEIGHTS = {
    "inclusion_rate": 0.40,
    "name_similarity": 0.10,
    "comment_similarity": 0.10,
    "type_compatibility": 0.20,
    "jaccard_index": 0.20,
}


def _mk_pipeline():
    """绕过 __init__（不连 DB）构造轻量 pipeline，仅保留合并阶段依赖"""
    pipeline = RelationshipDiscoveryPipeline.__new__(RelationshipDiscoveryPipeline)
    pipeline.rel_id_salt = ""
    pipeline.scorer = SimpleNamespace(weights=dict(FIVE_DIM_WEIGHTS))
    return pipeline


def _cand(
        table: str,
        cols: list,
        target_table: str,
        target_cols: list,
        origin: str,
        key_origin,
        cardinality: str,
        score: float,
        reverse_inclusion: float = 0.5,
        score_details: dict = None,
):
    """构造评分后候选（含 _reverse_inclusion_rate 内部字段）"""
    src = {"object_info": {"schema_name": "public", "object_name": table}}
    tgt = {"object_info": {"schema_name": "public", "object_name": target_table}}
    sd = score_details or {
        "inclusion_rate": 0.5, "name_similarity": 1.0, "comment_similarity": 0.5,
        "type_compatibility": 1.0, "jaccard_index": 0.5,
    }
    candidate = {
        "source": src, "target": tgt,
        "source_columns": list(cols), "target_columns": list(target_cols),
        "candidate_origin": origin, "cardinality": cardinality,
        "composite_score": score, "score_details": dict(sd),
        "_reverse_inclusion_rate": reverse_inclusion,
    }
    if key_origin is not None:
        candidate["key_origin"] = key_origin
    return candidate


def _composite(sd, weights=None):
    weights = weights or FIVE_DIM_WEIGHTS
    return sum(sd[d] * weights[d] for d in sd)


def _dir_of(merged):
    return (
        merged["source"]["object_info"]["object_name"],
        merged["target"]["object_info"]["object_name"],
    )


class TestPostScoreCorrection:
    """① 评分后纠偏（按来源分别处理，doc 19 §3.2.2）"""

    def test_llm_1n_flipped_and_rescored(self):
        pipeline = _mk_pipeline()
        llm = _cand("products", ["id"], "orders", ["pid"], "llm", None,
                    "1:N", score=0.6, reverse_inclusion=0.9)
        corrected = pipeline._post_score_correction([], [llm])
        assert len(corrected) == 1
        c = corrected[0]
        # 翻转:products->orders 变 orders->products,基数改写 N:1
        assert _dir_of(c) == ("orders", "products")
        assert c["cardinality"] == "N:1"
        assert c["score_details"]["inclusion_rate"] == 0.9
        expected = _composite(c["score_details"])
        assert abs(c["composite_score"] - expected) < 1e-9

    def test_physical_rule_cardinality_fixed_without_flip(self):
        pipeline = _mk_pipeline()
        # 物理键规则候选:方向 = 关联字段表→键表(orders.category_id → categories.id)
        phys_1n = _cand("orders", ["category_id"], "categories", ["id"], "rule",
                        "physical", "1:N", score=0.7)
        phys_mn = _cand("orders", ["category_id"], "categories", ["id"], "rule",
                        "physical", "M:N", score=0.7)
        corrected = pipeline._post_score_correction([phys_1n, phys_mn], [])
        assert [c["cardinality"] for c in corrected] == ["1:1", "N:1"]
        # 不翻转:方向保持 orders->categories,分数不重算
        for c in corrected:
            assert _dir_of(c) == ("orders", "categories")
            assert c["composite_score"] == 0.7

    def test_logical_rule_invalid_dropped(self):
        pipeline = _mk_pipeline()
        logical_1n = _cand("orders", ["category_id"], "categories", ["id"], "rule",
                           "logical", "1:N", score=0.7)
        logical_n1 = _cand("orders", ["category_id"], "categories", ["id"], "rule",
                           "logical", "N:1", score=0.7)
        corrected = pipeline._post_score_correction([logical_1n, logical_n1], [])
        assert len(corrected) == 1
        assert corrected[0]["cardinality"] == "N:1"

    def test_llm_mn_kept_as_symmetric(self):
        pipeline = _mk_pipeline()
        llm_mn = _cand("products", ["id"], "orders", ["pid"], "llm", None,
                       "M:N", score=0.5)
        corrected = pipeline._post_score_correction([], [llm_mn])
        assert len(corrected) == 1
        assert corrected[0]["cardinality"] == "M:N"


class TestMergeGroupCardinalityAndDirection:
    """②③④ 分组 / 基数决策 / 方向决策"""

    def test_opposite_directions_still_merge_rule_n1_wins(self):
        """规则 orders→categories N:1 与 LLM M:N(字典序应翻成 categories→orders)
        → 无向分组后仍合并,最终 N:1、方向 orders→categories(doc 19 §5)"""
        pipeline = _mk_pipeline()
        rule = _cand("orders", ["category_id"], "categories", ["id"], "rule",
                     "physical", "N:1", score=0.82, reverse_inclusion=0.1)
        llm_mn = _cand("orders", ["category_id"], "categories", ["id"], "llm",
                       None, "M:N", score=0.88, reverse_inclusion=0.9)
        merged = pipeline._merge_scored_candidates([rule], [llm_mn])
        assert len(merged) == 1
        m = merged[0]
        assert m["cardinality"] == "N:1"
        assert _dir_of(m) == ("orders", "categories")
        # 分数取高分候选(LLM 0.88),但基数/方向服从键证据
        assert m["composite_score"] == 0.88
        assert m["candidate_origin"] == "rule+llm"
        assert m["key_origin"] == "physical"

    def test_bidirectional_physical_rules_yield_1_1(self):
        """双向物理规则(两次采样各自 N:1)→ 组内最终 1:1(doc 19 §5)"""
        pipeline = _mk_pipeline()
        a_to_b = _cand("a", ["id"], "b", ["id"], "rule", "physical", "N:1", 0.7)
        b_to_a = _cand("b", ["id"], "a", ["id"], "rule", "physical", "N:1", 0.7)
        merged = pipeline._merge_scored_candidates([a_to_b, b_to_a], [])
        assert len(merged) == 1
        assert merged[0]["cardinality"] == "1:1"

    def test_bidirectional_logical_rules_yield_1_1(self):
        pipeline = _mk_pipeline()
        a_to_b = _cand("a", ["id"], "b", ["id"], "rule", "logical", "N:1", 0.7)
        b_to_a = _cand("b", ["id"], "a", ["id"], "rule", "logical", "N:1", 0.7)
        merged = pipeline._merge_scored_candidates([a_to_b, b_to_a], [])
        assert len(merged) == 1
        assert merged[0]["cardinality"] == "1:1"

    def test_physical_beats_logical_when_opposing(self):
        """物理规则与反向逻辑规则冲突 → 物理规则优先(方向 + 基数)

        决策优先级第 2 条:只有一个方向有物理键规则证据 → 使用该物理候选的
        cardinality(N:1);方向取最高优先级(物理)规则候选方向。
        """
        pipeline = _mk_pipeline()
        phys_a_to_b = _cand("a", ["id"], "b", ["id"], "rule", "physical", "N:1", 0.7)
        logic_b_to_a = _cand("b", ["id"], "a", ["id"], "rule", "logical", "N:1", 0.9)
        merged = pipeline._merge_scored_candidates([phys_a_to_b, logic_b_to_a], [])
        assert len(merged) == 1
        m = merged[0]
        assert m["cardinality"] == "N:1"
        assert _dir_of(m) == ("a", "b")
        assert m["key_origin"] == "physical"
        # 内容取"规范化到最终方向后重算"的最高分:逻辑候选翻转到 a->b 后
        # inclusion 取 reverse(0.5)、总分降为 0.65,物理候选 0.7 胜出
        assert m["composite_score"] == 0.7

    def test_pure_llm_1_1_uses_lexicographic_direction(self):
        """纯 LLM 1:1 反向对 → 直接按端点字典序(方向与分数无关)"""
        pipeline = _mk_pipeline()
        a_to_b = _cand("a", ["id"], "b", ["id"], "llm", None, "1:1", 0.9)
        b_to_a = _cand("b", ["id"], "a", ["id"], "llm", None, "1:1", 0.5)
        merged = pipeline._merge_scored_candidates([a_to_b, b_to_a], [])
        assert len(merged) == 1
        # 字典序:a < b → 方向 a->b(无论分数高低)
        assert _dir_of(merged[0]) == ("a", "b")
        # 内容取高分候选(0.9)
        assert merged[0]["composite_score"] == 0.9

    def test_pure_llm_n1_wins_by_tiebreak_at_correction_time(self):
        """纯 LLM N:1 方向 = 纠偏完成时获胜候选方向(两阶段,无循环)"""
        pipeline = _mk_pipeline()
        a_to_b = _cand("a", ["id"], "b", ["id"], "llm", None, "N:1", 0.9)
        b_to_a = _cand("b", ["id"], "a", ["id"], "llm", None, "N:1", 0.7)
        merged = pipeline._merge_scored_candidates([a_to_b, b_to_a], [])
        assert len(merged) == 1
        assert _dir_of(merged[0]) == ("a", "b")
        assert merged[0]["cardinality"] == "N:1"

    def test_tiebreak_evidence_rank_prefers_rule_content(self):
        """规则与 LLM 总分相同 → 证据优先级(物理规则 > LLM)选择评分内容"""
        pipeline = _mk_pipeline()
        rule = _cand("a", ["id"], "b", ["id"], "rule", "physical", "N:1", 0.8)
        llm = _cand("a", ["id"], "b", ["id"], "llm", None, "N:1", 0.8)
        merged = pipeline._merge_scored_candidates([rule], [llm])
        assert len(merged) == 1
        m = merged[0]
        # 同分时规则证据的内容胜出(score_details 属于规则候选)
        assert m["candidate_origin"] == "rule+llm"
        assert m["key_origin"] == "physical"

    def test_tiebreak_same_score_uses_unsigned_signature(self):
        """同分纯 LLM 候选按未加盐签名升序决胜,与输入顺序无关"""
        pipeline = _mk_pipeline()
        a_to_b = _cand("a", ["id"], "b", ["id"], "llm", None, "N:1", 0.8)
        b_to_a = _cand("b", ["id"], "a", ["id"], "llm", None, "N:1", 0.8)
        merged_1 = pipeline._merge_scored_candidates([a_to_b, b_to_a], [])
        merged_2 = pipeline._merge_scored_candidates([b_to_a, a_to_b], [])
        assert _dir_of(merged_1[0]) == _dir_of(merged_2[0])

    def test_final_relationship_id_generated_after_merge(self):
        """⑦ 最终有向 ID 在组内基数与方向确定后生成"""
        from metaweave.core.relationships.repository import MetadataRepository

        pipeline = _mk_pipeline()
        rule = _cand("orders", ["category_id"], "categories", ["id"], "rule",
                     "physical", "N:1", 0.8)
        merged = pipeline._merge_scored_candidates([rule], [])
        expected = MetadataRepository.compute_relationship_id(
            "public", "orders", ["category_id"],
            "public", "categories", ["id"],
            rel_id_salt="",
        )
        assert merged[0]["_relationship_id"] == expected

    def test_key_origin_follows_final_direction_not_high_score_reverse(self):
        """字段级分离:反向高分候选不被整体复制,key_origin 与最终方向一致
        (doc 19 §5:双向规则决胜)"""
        pipeline = _mk_pipeline()
        # A->B:target B 是物理键,分数 0.75
        phys_a_to_b = _cand("a", ["id"], "b", ["id"], "rule", "physical", "N:1", 0.75)
        # B->A:target A 是逻辑键,分数 0.85
        logic_b_to_a = _cand("b", ["id"], "a", ["id"], "rule", "logical", "N:1", 0.85)
        merged = pipeline._merge_scored_candidates([phys_a_to_b, logic_b_to_a], [])
        assert len(merged) == 1
        m = merged[0]
        # 单方向物理证据 → 基数取物理候选的 N:1;方向:物理键方向优先 → a->b
        assert m["cardinality"] == "N:1"
        assert _dir_of(m) == ("a", "b")
        # key_origin 来自支持最终方向的物理候选,不从反向高分候选整体复制
        assert m["key_origin"] == "physical"
        # 评分内容取"规范化到最终方向后重算"的最高分:逻辑候选翻转后
        # 总分降为 0.65,物理候选 0.75 胜出
        assert m["composite_score"] == 0.75
