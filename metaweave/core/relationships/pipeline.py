"""关系发现管道

主控制器，协调整个关系发现流程（doc 15 统一改造版）。

统一管线：
1. JSON加载 + 外键直通（登记身份）
2. 规则候选生成 + （可选）LLM 候选产出 → 合并入池 → 池内统一去重
   （含最小键过滤）→ 排除与物理 FK 重复的候选
3. 候选评分（5维度 + 数据库采样）
4. 决策过滤 + 抑制
5. 结果输出（JSON + Markdown）
"""

import logging
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from metaweave.core.metadata.connector import DatabaseConnector
from metaweave.core.relationships.models import RelationshipDiscoveryResult
from metaweave.core.relationships.repository import MetadataRepository
from metaweave.core.relationships.candidate_generator import CandidateGenerator
from metaweave.core.relationships.llm_relationship_discovery import LLMRelationshipDiscovery
from metaweave.core.relationships.scorer import RelationshipScorer
from metaweave.core.relationships.decision_engine import DecisionEngine
from metaweave.core.relationships.writer import RelationshipWriter
from metaweave.core.relationships.name_similarity import (
    InvalidNameSimilarityConfig,
    NameSimilarityService,
)
from metaweave.utils.file_utils import get_project_root
from metaweave.utils.logger import get_metaweave_logger
from services.config_loader import ConfigLoader

logger = get_metaweave_logger("relationships.pipeline")


class RelationshipDiscoveryPipeline:
    """关系发现管道

    协调统一管线的各阶段：
    1. JSON加载 + 外键直通
    2. 候选生成（规则 + 可选 LLM，池内统一去重）
    3. 候选评分（5维度 + 数据库采样）
    4. 决策过滤 + 抑制
    5. 结果输出（JSON + Markdown）
    """

    def __init__(
            self,
            config_path: Path,
            domain_filter: Optional[str] = None,
            cross_domain: bool = False,
            domain_resolver: "Optional[Any]" = None,
    ):
        """初始化关系发现管道

        Args:
            config_path: 配置文件路径
            domain_filter: --domain 参数（None/"all"/逗号分隔 domain 名），见 3.13
            cross_domain: 是否包含跨域表对
            domain_resolver: DomainResolver 实例（domain_filter 生效时必须提供）
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.rel_config = (self.config.get("relationships") or {}).copy()
        for key in ["decision", "weights"]:
            if key in self.config and key not in self.rel_config:
                self.rel_config[key] = self.config[key]
        # 关系评分阶段的数据库采样行数上限：统一使用 sampling.sample_size
        self.rel_config["sample_size"] = (self.config.get("sampling") or {}).get("sample_size", 1000)
        self.embedding_config = self.config.get("embedding") or {}

        # Domain 相关（见 3.13：规则与 LLM 候选共用统一表对范围）
        self.domain_filter = domain_filter
        self.cross_domain = cross_domain
        self.domain_resolver = domain_resolver

        # 获取JSON目录（支持直接配置 json_directory，或从 output_dir 推导）
        output_config = self.config.get("output", {})
        json_directory = output_config.get("json_directory")
        if json_directory:
            self.json_dir = get_project_root() / json_directory
        else:
            # Fallback: 从 output_dir 推导
            output_dir = output_config.get("output_dir", "output")
            self.json_dir = get_project_root() / output_dir / "json"

        config_source = "显式配置" if json_directory else "自动推导"
        logger.info(f"关系发现管道已初始化: json_dir={self.json_dir} ({config_source})")

        # 初始化数据库连接器（从database节点获取配置）
        db_config = self.config.get("database", {})
        self.connector = DatabaseConnector(db_config)

        # 初始化各模块（传入配置）
        rel_id_salt = output_config.get("rel_id_salt", "")
        self.rel_id_salt = rel_id_salt
        # 逻辑键置信度阈值与规则候选生成同口径（doc 19 §3.2.3，不得硬编码）
        candidate_matching = (self.rel_config or {}).get("candidate_matching") or {}
        logical_key_min_confidence = candidate_matching.get(
            "logical_key_min_confidence", 0.8
        )
        self.repository = MetadataRepository(
            self.json_dir,
            rel_id_salt=rel_id_salt,
            logical_key_min_confidence=logical_key_min_confidence,
        )

        # name similarity service（method 唯一取值为 embedding；无 embedding 配置时降级）
        #
        # 注意：显式非法配置（如 method: string，InvalidNameSimilarityConfig）
        # 必须继续向上传播、直接报错——doc 4.3 要求旧配置"检测到即报错，不静默
        # 兼容"。只有 EmbeddingService 因缺少 active/providers/model/api_key
        # 等而失败（即"无 embedding 环境"）才属于 doc 15 第5节的降级语义，
        # 在此捕获并降级为同名短路 / 禁用注释闸。两者都是 ValueError 子类，
        # 必须先窄后宽地分开捕获，不能用一个 except Exception 把两种情况混在一起。
        name_sim_config = self.rel_config.get("name_similarity", {})
        try:
            self.name_similarity_service = NameSimilarityService(name_sim_config, self.embedding_config)
        except InvalidNameSimilarityConfig:
            raise
        except Exception as exc:
            logger.warning("名称相似度服务初始化失败，按降级语义运行（同名短路/无注释闸）: %s", exc)
            self.name_similarity_service = None

        # candidate_generator（统一规则+LLM候选生成器）
        self.candidate_generator = CandidateGenerator(
            self.rel_config, self.name_similarity_service, rel_id_salt=rel_id_salt
        )

        # LLM 候选来源开关（放在 llm 节点之外，避免 resolver 白名单报错，见 4.1）
        llm_candidates_config = self.rel_config.get("llm_candidates", {}) or {}
        self.llm_candidates_enabled = bool(llm_candidates_config.get("enabled", True))
        self.llm_top_k = self._parse_llm_top_k(llm_candidates_config.get("top_k", 50))

        self.llm_producer: Optional[LLMRelationshipDiscovery] = None
        if self.llm_candidates_enabled:
            self.llm_producer = LLMRelationshipDiscovery(
                config=self.config,
                domain_filter=domain_filter,
                cross_domain=cross_domain,
                domain_resolver=domain_resolver,
            )

        # scorer需要connector和config（传入关系配置）
        self.scorer = RelationshipScorer(self.rel_config, self.connector, self.name_similarity_service)

        # decision_engine（传入top-level config）
        self.decision_engine = DecisionEngine(self.config)

        # writer（传入top-level config）
        self.writer = RelationshipWriter(self.config)

    @staticmethod
    def _parse_llm_top_k(raw: Any) -> int:
        """解析 llm_candidates.top_k：必须是 ≥1 的正整数（见 doc 15 §3.9 / §4.1）。

        关闭 LLM 候选请用 `llm_candidates.enabled: false`，不得把 top_k 设为 0
        表示"不限量"——top_k 的存在目的就是限制评分阶段 DB 采样成本。
        """
        if raw is None:
            return 50
        try:
            top_k = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"relationships.llm_candidates.top_k 必须是正整数，检测到: {raw!r}"
            ) from exc
        if top_k < 1:
            raise ValueError(
                f"relationships.llm_candidates.top_k 必须是正整数（≥1），"
                f"检测到: {top_k}。关闭 LLM 候选请设置 llm_candidates.enabled: false，"
                f"而不是把 top_k 设为 0 / 负数。"
            )
        return top_k

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件（使用ConfigLoader处理环境变量替换）"""
        try:
            config_loader = ConfigLoader(str(self.config_path))
            config = config_loader.load()
            if not config:
                raise ValueError(f"配置文件加载失败: {self.config_path}")
            logger.info(f"配置文件加载成功: {self.config_path}")
            return config
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise

    def _resolve_table_pairs(self, tables: Dict[str, dict]) -> List[Tuple[str, str]]:
        """根据 domain 配置生成表对列表（规则与 LLM 候选共用，见 3.13）

        domain_filter 为空时，无论 cross_domain 是什么，都走全量两两组合路径
        （现状行为不变）。
        """
        if not self.domain_filter:
            return list(combinations(tables.keys(), 2))

        if self.domain_resolver is None:
            raise ValueError(
                f"domain={self.domain_filter} 已生效，但未提供 DomainResolver。"
                f"请确认 domains 配置文件存在且已正确加载"
            )
        return self.domain_resolver.resolve_table_pairs(
            available_tables=list(tables.keys()),
            domain_filter=self.domain_filter,
            cross_domain=bool(self.cross_domain),
        )

    def discover(self) -> RelationshipDiscoveryResult:
        """执行统一管线的关系发现

        Returns:
            关系发现结果
        """
        result = RelationshipDiscoveryResult(success=True)

        try:
            logger.info("=" * 60)
            logger.info("开始关系发现")
            logger.info("=" * 60)

            # Stage 1: JSON加载 + 外键直通
            logger.info("阶段1: 加载JSON元数据并提取外键直通关系")
            tables = self.repository.load_all_tables()
            fk_relations, fk_relationship_ids = self.repository.collect_foreign_keys(tables)

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("表样例: %s", list(tables.keys())[:3])
                logger.debug(
                    "外键直通样例: %s",
                    [self._format_relation_debug(rel) for rel in fk_relations[:3]],
                )

            result.foreign_key_relations = len(fk_relations)
            logger.info(f"外键直通关系: {result.foreign_key_relations} 个")

            # 统一表对范围（见 3.13）
            table_pairs = self._resolve_table_pairs(tables)
            logger.info(f"表对范围: {len(table_pairs)} 对（domain={self.domain_filter!r}, cross_domain={self.cross_domain}）")

            # Stage 2a: （可选）LLM 候选产出
            llm_raw_candidates: List[Dict[str, Any]] = []
            llm_stats = {"llm_total_pairs": 0, "llm_success_pairs": 0, "llm_failed_pairs": 0}
            if self.llm_candidates_enabled and self.llm_producer is not None:
                logger.info("阶段2a: LLM 候选产出（llm_candidates.enabled=true）")
                try:
                    llm_raw_candidates = self.llm_producer.run_discover(tables, table_pairs)
                except Exception as exc:
                    logger.error("LLM 候选产出整体失败，降级为纯规则管线: %s", exc, exc_info=True)
                    result.add_error(f"LLM 候选产出失败（已降级为纯规则管线）: {exc}")
                    llm_raw_candidates = []
                llm_stats = {
                    "llm_total_pairs": self.llm_producer.total_pairs,
                    "llm_success_pairs": self.llm_producer.success_pairs,
                    "llm_failed_pairs": self.llm_producer.failed_pairs,
                }
                logger.info(
                    "LLM 候选产出完成: 成功 %s/%s 个表对，失败 %s 个，原始候选 %s 个",
                    llm_stats["llm_success_pairs"], llm_stats["llm_total_pairs"],
                    llm_stats["llm_failed_pairs"], len(llm_raw_candidates),
                )
            else:
                logger.info("阶段2a: LLM 候选已禁用（llm_candidates.enabled=false），纯规则管线")

            # Stage 2b: 规则池与 LLM 池独立生成（各自同向去重/最小键过滤/FK 排除）
            logger.info("阶段2b: 生成候选池（规则池 / LLM 池独立出口）")
            rule_pool, llm_pool = self.candidate_generator.generate_candidates(
                tables, table_pairs, fk_relationship_ids,
                llm_raw_candidates=llm_raw_candidates,
                llm_top_k=self.llm_top_k,
            )
            logger.info(f"候选池: 规则 {len(rule_pool)} 个 / LLM {len(llm_pool)} 个")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "规则池样例: %s",
                    [self._format_candidate_debug(c) for c in rule_pool[:3]],
                )
                logger.debug(
                    "LLM 池样例: %s",
                    [self._format_candidate_debug(c) for c in llm_pool[:3]],
                )

            result.llm_candidates_enabled = self.llm_candidates_enabled
            result.llm_total_pairs = llm_stats["llm_total_pairs"]
            result.llm_success_pairs = llm_stats["llm_success_pairs"]
            result.llm_failed_pairs = llm_stats["llm_failed_pairs"]

            # Stage 3: 分开评分（规则结果、LLM 结果，doc 19 §3.1）
            logger.info("阶段3: 分开评分（规则池 / LLM 池，5维度 + 数据库采样）")
            scored_rule = self.scorer.score_candidates(rule_pool, tables)
            scored_llm = self.scorer.score_candidates(llm_pool, tables)
            logger.info(f"评分完成: 规则 {len(scored_rule)} 个 / LLM {len(scored_llm)} 个")

            # Stage 3.5: 合并阶段（七步，doc 19 §3.3）
            logger.info("阶段3.5: 合并阶段（纠偏 → 无向分组 → 基数 → 方向 → 规范重算 → 字段合并 → 生成 ID）")
            merged_candidates = self._merge_scored_candidates(scored_rule, scored_llm)
            logger.info(f"合并完成: {len(merged_candidates)} 个")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "合并样例: %s",
                    [self._format_candidate_debug(c) for c in merged_candidates[:3]],
                )

            # Stage 4: 决策过滤 + 抑制（输入 = 合并后的完整关系集）
            logger.info("阶段4: 决策过滤和抑制规则")
            inferred_relations, suppressed, below_threshold = self.decision_engine.filter_and_suppress(
                merged_candidates
            )

            result.inferred_relations = len(inferred_relations)
            result.suppressed_count = len(suppressed)
            result.below_threshold_count = len(below_threshold)
            logger.info(
                "推断关系: %s 个，未达阈值: %s 个，复合键抑制: %s 个",
                result.inferred_relations,
                result.below_threshold_count,
                result.suppressed_count,
            )
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "接受样例: %s",
                    [self._format_relation_debug(rel) for rel in inferred_relations[:3]],
                )
                logger.debug(
                    "被抑制样例: %s",
                    [self._format_candidate_debug(c) for c in suppressed[:3]],
                )
                logger.debug(
                    "未达阈值样例: %s",
                    [self._format_candidate_debug(c) for c in below_threshold[:3]],
                )

            # 统计置信度分布
            decision_config = self.config.get("decision", {})
            high_threshold = decision_config.get("high_confidence_threshold", 0.90)
            medium_threshold = decision_config.get("medium_confidence_threshold", 0.80)

            for rel in inferred_relations:
                if rel.composite_score and rel.composite_score >= high_threshold:
                    result.high_confidence_count += 1
                elif rel.composite_score and rel.composite_score >= medium_threshold:
                    result.medium_confidence_count += 1

            # Stage 5: 输出结果
            logger.info("阶段5: 输出结果（JSON + Markdown）")
            all_relations = fk_relations + inferred_relations
            result.total_relations = len(all_relations)

            extra_statistics = {
                "database_queries_executed": self.scorer.query_count,
                **llm_stats,
            }
            output_files = self.writer.write_results(
                all_relations, suppressed, self.config, tables,
                generated_by=self.writer.generated_by_label(self.llm_candidates_enabled),
                extra_statistics=extra_statistics,
            )
            for file_path in output_files:
                result.add_output_file(file_path)
                logger.debug("输出文件: %s", file_path)

            logger.info("=" * 60)
            logger.info("关系发现完成")
            logger.info(f"总关系数: {result.total_relations}")
            logger.info(f"  - 外键直通: {result.foreign_key_relations}")
            logger.info(f"  - 推断关系: {result.inferred_relations}")
            logger.info(f"  - 高置信度: {result.high_confidence_count}")
            logger.info(f"  - 中置信度: {result.medium_confidence_count}")
            logger.info(f"  - 未达阈值: {result.below_threshold_count}")
            logger.info(f"  - 复合键抑制: {result.suppressed_count}")
            if self.llm_candidates_enabled:
                logger.info(
                    f"  - LLM 候选产出: 成功 {llm_stats['llm_success_pairs']}/{llm_stats['llm_total_pairs']} "
                    f"个表对，失败 {llm_stats['llm_failed_pairs']} 个"
                )
            logger.info(f"输出文件: {len(result.output_files)} 个")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"关系发现失败: {e}", exc_info=True)
            result.add_error(str(e))

        finally:
            # 关闭数据库连接
            self.connector.close()

        return result

    # ------------------------------------------------------------------
    # 合并阶段（七步，doc 19 §3.3）
    # ------------------------------------------------------------------

    _EVIDENCE_RANK = {"physical": 2, "logical": 1, "llm": 0}
    _FIXED_SCORE_DIMS = (
        "inclusion_rate", "name_similarity", "comment_similarity",
        "type_compatibility", "jaccard_index",
    )

    @staticmethod
    def _candidate_dir(candidate: Dict[str, Any]) -> Tuple[str, str]:
        """候选方向标识:(from 表全名, to 表全名)"""
        src_info = candidate["source"].get("table_info", {})
        tgt_info = candidate["target"].get("table_info", {})
        return (
            f"{src_info.get('schema_name')}.{src_info.get('table_name')}",
            f"{tgt_info.get('schema_name')}.{tgt_info.get('table_name')}",
        )

    @staticmethod
    def _evidence_rank(candidate: Dict[str, Any]) -> int:
        """证据优先级:物理规则 > 逻辑规则 > LLM(doc 19 §3.3 候选决胜键)"""
        if candidate.get("candidate_origin") != "rule":
            return RelationshipDiscoveryPipeline._EVIDENCE_RANK["llm"]
        return RelationshipDiscoveryPipeline._EVIDENCE_RANK.get(
            candidate.get("key_origin"), 0
        )

    def _flip_candidate(self, candidate: Dict[str, Any]) -> None:
        """交换端点与两侧列,并取 reverse_inclusion_rate 重算 inclusion 与总分

        (doc 19 §3.2.2:不新增 DB 查询、不暴露样本集合)
        """
        candidate["source"], candidate["target"] = candidate["target"], candidate["source"]
        candidate["source_columns"], candidate["target_columns"] = (
            candidate["target_columns"], candidate["source_columns"],
        )
        score_details = dict(candidate.get("score_details") or {})
        old_inclusion = float(score_details.get("inclusion_rate", 0.0))
        new_inclusion = float(
            candidate.get("_reverse_inclusion_rate", old_inclusion)
        )
        score_details["inclusion_rate"] = new_inclusion
        candidate["score_details"] = score_details
        candidate["_reverse_inclusion_rate"] = old_inclusion
        # 复用 scorer 的共享纯函数重算总分（权重单一来源，不硬编码）
        candidate["composite_score"] = RelationshipScorer.recompute_composite_score(
            score_details, self.scorer.weights
        )

    def _post_score_correction(
            self,
            scored_rule: List[Dict[str, Any]],
            scored_llm: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """① 评分后纠偏(按来源分别处理,doc 19 §3.2.2)

        - LLM 候选:1:N → 翻转 from/to、改写 N:1 并重算;M:N → 对称保留 + 日志;
        - 物理键规则候选:不执行方向翻转——1:N → 按 source 唯一修正为 1:1,
          M:N → 按 source 不唯一修正为 N:1,均记录采样与约束冲突 warning;
        - 逻辑键规则候选:1:N / M:N → 本次评分未复现 target 的逻辑键唯一性,
          丢弃候选并告警。
        """
        corrected: List[Dict[str, Any]] = []

        for candidate in scored_rule:
            key_origin = candidate.get("key_origin")
            cardinality = candidate.get("cardinality")
            if key_origin == "physical":
                if cardinality == "1:N":
                    logger.warning(
                        "物理键规则候选采样与约束冲突,按 source 唯一修正为 1:1: %s",
                        self._format_candidate_debug(candidate),
                    )
                    candidate["cardinality"] = "1:1"
                elif cardinality == "M:N":
                    logger.warning(
                        "物理键规则候选采样与约束冲突,按 source 不唯一修正为 N:1: %s",
                        self._format_candidate_debug(candidate),
                    )
                    candidate["cardinality"] = "N:1"
                corrected.append(candidate)
            elif key_origin == "logical":
                if cardinality in ("1:N", "M:N"):
                    logger.warning(
                        "逻辑键规则候选评分未复现 target 逻辑键唯一性(%s),丢弃: %s",
                        cardinality, self._format_candidate_debug(candidate),
                    )
                    continue
                corrected.append(candidate)
            else:
                corrected.append(candidate)

        for candidate in scored_llm:
            cardinality = candidate.get("cardinality")
            if cardinality == "1:N":
                logger.info(
                    "LLM 候选数据判反(1:N),翻转并改写 N:1: %s",
                    self._format_candidate_debug(candidate),
                )
                self._flip_candidate(candidate)
                candidate["cardinality"] = "N:1"
            elif cardinality == "M:N":
                logger.info(
                    "LLM 候选 M:N,按对称推断关联保留(方向由合并阶段字典序决定): %s",
                    self._format_candidate_debug(candidate),
                )
            corrected.append(candidate)

        return corrected

    def _group_by_undirected_identity(
            self,
            candidates: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """② 无向身份分组:所有评分后候选按无向身份进组(doc 19 §3.3)。

        不依赖方向——不同 cardinality 的同一关系在各自方向规范化后可能变成
        相反方向,先按无向身份分组才能执行组内 cardinality 决策。
        """
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for candidate in candidates:
            src_info = candidate["source"].get("table_info", {})
            tgt_info = candidate["target"].get("table_info", {})
            uid = MetadataRepository.compute_undirected_identity(
                source_schema=src_info.get("schema_name"),
                source_table=src_info.get("table_name"),
                source_columns=candidate["source_columns"],
                target_schema=tgt_info.get("schema_name"),
                target_table=tgt_info.get("table_name"),
                target_columns=candidate["target_columns"],
            )
            groups.setdefault(uid, []).append(candidate)
        return groups

    def _tiebreak_key(self, candidate: Dict[str, Any]) -> Tuple:
        """候选决胜键(doc 19 §3.3):1) composite_score 降序;2) 证据优先级;
        3) 纠偏完成时(规范到最终方向之前)的未加盐有向签名升序;
        4) score_details 固定维度元组升序兜底。返回升序 key(取最小者获胜)。
        """
        score_details = candidate.get("score_details") or {}
        return (
            -float(candidate.get("composite_score") or 0.0),
            -self._evidence_rank(candidate),
            candidate.get(
                "_pre_normalize_signature",
                CandidateGenerator._directed_unsigned_signature(candidate),
            ),
            tuple(float(score_details.get(dim, 0.0)) for dim in self._FIXED_SCORE_DIMS),
        )

    def _pick_winner(self, group: List[Dict[str, Any]]) -> Dict[str, Any]:
        """按候选决胜键选组内获胜者(返回升序 key 最小者)"""
        return min(group, key=self._tiebreak_key)

    def _decide_group_cardinality(
            self,
            group: List[Dict[str, Any]],
    ) -> str:
        """③ 组内 cardinality 决策(先于方向,doc 19 §3.3):
        1. 两个方向都有物理键规则证据 → 1:1;
        2. 只有一个方向有物理键规则证据 → 该物理候选修正后的 cardinality;
        3. 无物理证据、两个方向都有有效逻辑键证据 → 1:1;
        4. 只有一个方向有有效逻辑键证据 → 该逻辑候选的 cardinality;
        5. 纯 LLM → 纠偏完成时(最终方向尚未确定)获胜候选的 cardinality;
        6. 不得出现 1:N。
        """
        physical_dirs = {
            self._candidate_dir(c)
            for c in group
            if c.get("candidate_origin") == "rule" and c.get("key_origin") == "physical"
        }
        if len(physical_dirs) >= 2:
            return "1:1"
        if len(physical_dirs) == 1:
            physical_candidate = next(
                c for c in group
                if c.get("candidate_origin") == "rule" and c.get("key_origin") == "physical"
            )
            return physical_candidate.get("cardinality", "N:1")

        logical_dirs = {
            self._candidate_dir(c)
            for c in group
            if c.get("candidate_origin") == "rule" and c.get("key_origin") == "logical"
        }
        if len(logical_dirs) >= 2:
            return "1:1"
        if len(logical_dirs) == 1:
            logical_candidate = next(
                c for c in group
                if c.get("candidate_origin") == "rule" and c.get("key_origin") == "logical"
            )
            return logical_candidate.get("cardinality", "N:1")

        winner = self._pick_winner(group)
        cardinality = winner.get("cardinality", "N:1")
        if cardinality == "1:N":
            # LLM 纠偏后不应出现 1:N,防御性兜底
            logger.warning("纯 LLM 组出现 1:N 获胜候选,改写为 N:1: %s", self._format_candidate_debug(winner))
            cardinality = "N:1"
        return cardinality

    def _lexicographic_direction(
            self,
            group: List[Dict[str, Any]],
    ) -> Tuple[str, str]:
        """字典序方向(doc 19 §3.3):端点 = (schema, table, sorted(columns)),
        比较键 (casefold, 原始值) 逐级比较,较小的一端固定为 from。
        """
        sample = group[0]
        src_info = sample["source"].get("table_info", {})
        tgt_info = sample["target"].get("table_info", {})

        def endpoint_key(info: dict, columns: List[str]) -> Tuple:
            return (
                (info.get("schema_name", "").casefold(), info.get("schema_name", "")),
                (info.get("table_name", "").casefold(), info.get("table_name", "")),
                tuple((col.casefold(), col) for col in sorted(columns)),
            )

        left = endpoint_key(src_info, sample["source_columns"])
        right = endpoint_key(tgt_info, sample["target_columns"])
        src_full, tgt_full = self._candidate_dir(sample)
        if left <= right:
            return src_full, tgt_full
        return tgt_full, src_full

    def _decide_group_direction(
            self,
            group: List[Dict[str, Any]],
            final_cardinality: str,
    ) -> Tuple[str, str]:
        """④ 按最终 cardinality 决定唯一方向(doc 19 §3.3):
        - N:1:有规则证据时使用最高优先级规则候选方向(引用方→键端);
          纯 LLM 使用决定最终 cardinality 的获胜候选方向;
        - 1:1:规则证据优先(物理 > 逻辑),两边键类型相同或纯 LLM → 字典序;
        - M:N:字典序(对称推断关联)。
        """
        rule_candidates = [
            c for c in group if c.get("candidate_origin") == "rule"
        ]

        if final_cardinality == "N:1":
            if rule_candidates:
                return self._candidate_dir(
                    min(rule_candidates, key=lambda c: -self._evidence_rank(c))
                )
            return self._candidate_dir(self._pick_winner(group))

        if final_cardinality == "1:1":
            rule_dirs = {self._candidate_dir(c) for c in rule_candidates}
            if len(rule_dirs) == 1:
                return next(iter(rule_dirs))
            physical_dirs = {
                self._candidate_dir(c)
                for c in rule_candidates
                if c.get("key_origin") == "physical"
            }
            if len(physical_dirs) == 1:
                return next(iter(physical_dirs))
            # 两边键类型相同(双物理/双逻辑)或纯 LLM → 字典序
            return self._lexicographic_direction(group)

        # M:N:对称推断关联,不称隐式外键,方向仅为确定性输出约定
        return self._lexicographic_direction(group)

    def _normalize_to_direction(
            self,
            candidate: Dict[str, Any],
            from_full: str,
    ) -> None:
        """⑤ 候选规范到最终方向:方向相反时翻转并取 reverse_inclusion_rate
        重算 composite_score(复用同次采样集合,不新增 DB 查询)"""
        src_full = self._candidate_dir(candidate)[0]
        if src_full != from_full:
            self._flip_candidate(candidate)

    def _merge_group_fields(
            self,
            group: List[Dict[str, Any]],
            winner: Dict[str, Any],
            final_cardinality: str,
            from_full: str,
    ) -> Dict[str, Any]:
        """⑥ 字段级合并(doc 19 §3.3):合并不是整对象覆盖,按字段拆分:
        - 端点:最终方向(规范化后与 winner 一致);
        - cardinality:组内决策结果;
        - key_origin:支持最终方向的规则候选(物理键优先;仅合并阶段内部信息);
        - candidate_origin:合并所有来源;
        - score_details/composite_score:规范化到最终方向后取最高分(决胜键)。
        """
        origins = {c.get("candidate_origin") for c in group}
        if "rule" in origins and "llm" in origins:
            candidate_origin = "rule+llm"
        elif origins == {"rule"}:
            candidate_origin = "rule"
        else:
            candidate_origin = "llm"

        key_origin = None
        for candidate in group:
            if candidate.get("candidate_origin") != "rule":
                continue
            pre_dir = candidate.get("_pre_normalize_dir")
            if pre_dir is None or pre_dir[0] != from_full:
                # 用规范前的方向判定"支持最终方向"
                continue
            if candidate.get("key_origin") == "physical":
                key_origin = "physical"
                break
            if key_origin is None:
                key_origin = candidate.get("key_origin")

        merged = {
            "source": winner["source"],
            "target": winner["target"],
            "source_columns": winner["source_columns"],
            "target_columns": winner["target_columns"],
            "cardinality": final_cardinality,
            "composite_score": winner.get("composite_score"),
            "score_details": winner.get("score_details"),
            "candidate_origin": candidate_origin,
            "_reverse_inclusion_rate": winner.get("_reverse_inclusion_rate"),
        }
        if key_origin is not None:
            merged["key_origin"] = key_origin
        return merged

    def _merge_scored_candidates(
            self,
            scored_rule: List[Dict[str, Any]],
            scored_llm: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """合并阶段主流程(七步,doc 19 §3.3):
        ① 评分后纠偏(按来源) → ② 无向身份分组 → ③ 组内 cardinality 决策
        → ④ 按最终 cardinality 决定唯一方向 → ⑤ 规范到最终方向 + 重算
        → ⑥ 字段级合并 → ⑦ 生成最终有向 relationship_id
        """
        corrected = self._post_score_correction(scored_rule, scored_llm)
        groups = self._group_by_undirected_identity(corrected)

        merged_list: List[Dict[str, Any]] = []
        for uid, group in groups.items():
            # 缓存规范化前签名与方向(决胜键与 key_origin 归属判定用,doc 19 §3.3)
            for candidate in group:
                candidate["_pre_normalize_signature"] = (
                    CandidateGenerator._directed_unsigned_signature(candidate)
                )
                candidate["_pre_normalize_dir"] = self._candidate_dir(candidate)

            final_cardinality = self._decide_group_cardinality(group)
            from_full, to_full = self._decide_group_direction(group, final_cardinality)

            for candidate in group:
                self._normalize_to_direction(candidate, from_full)

            winner = self._pick_winner(group)
            merged = self._merge_group_fields(
                group, winner, final_cardinality, from_full
            )
            # ⑦ 组内 cardinality 与方向确定、字段级合并完成后生成最终有向 ID
            src_info = merged["source"].get("table_info", {})
            tgt_info = merged["target"].get("table_info", {})
            merged["_relationship_id"] = MetadataRepository.compute_relationship_id(
                source_schema=src_info.get("schema_name"),
                source_table=src_info.get("table_name"),
                source_columns=merged["source_columns"],
                target_schema=tgt_info.get("schema_name"),
                target_table=tgt_info.get("table_name"),
                target_columns=merged["target_columns"],
                rel_id_salt=self.rel_id_salt,
            )
            logger.debug(
                "合并组 %s: %s 个候选 → %s,方向 %s->%s,来源 %s",
                uid, len(group), final_cardinality, from_full, to_full,
                merged.get("candidate_origin"),
            )
            merged_list.append(merged)

        logger.info(
            "合并阶段完成: %s 组 → %s 条(%s 条候选参与)",
            len(groups), len(merged_list), len(corrected),
        )
        return merged_list

    @staticmethod
    def _format_candidate_debug(candidate: Dict[str, Any]) -> str:
        if not candidate:
            return "<empty>"
        src_info = candidate["source"].get("table_info", {})
        tgt_info = candidate["target"].get("table_info", {})
        src = f"{src_info.get('schema_name')}.{src_info.get('table_name')}"
        tgt = f"{tgt_info.get('schema_name')}.{tgt_info.get('table_name')}"
        src_cols = ",".join(candidate.get("source_columns", []))
        tgt_cols = ",".join(candidate.get("target_columns", []))
        score = candidate.get("composite_score")
        origin = candidate.get("candidate_origin")
        return f"{src}[{src_cols}] -> {tgt}[{tgt_cols}] (origin={origin}, score={score})"

    @staticmethod
    def _format_relation_debug(rel) -> str:
        if rel is None:
            return "<empty>"
        return (
            f"{rel.source_schema}.{rel.source_table}[{', '.join(rel.source_columns)}] -> "
            f"{rel.target_schema}.{rel.target_table}[{', '.join(rel.target_columns)}]"
        )
