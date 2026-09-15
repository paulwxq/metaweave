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
        self.repository = MetadataRepository(self.json_dir, rel_id_salt=rel_id_salt)

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

            # Stage 2b: 规则候选生成 + LLM 候选合并入池 + 池内统一去重 + FK 排除
            logger.info("阶段2b: 生成候选关系（规则 + LLM 合并去重）")
            candidates = self.candidate_generator.generate_candidates(
                tables, table_pairs, fk_relationship_ids,
                llm_raw_candidates=llm_raw_candidates,
                llm_top_k=self.llm_top_k,
            )
            logger.info(f"候选关系: {len(candidates)} 个")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "候选样例: %s",
                    [self._format_candidate_debug(c) for c in candidates[:3]],
                )

            result.llm_candidates_enabled = self.llm_candidates_enabled
            result.llm_total_pairs = llm_stats["llm_total_pairs"]
            result.llm_success_pairs = llm_stats["llm_success_pairs"]
            result.llm_failed_pairs = llm_stats["llm_failed_pairs"]

            # Stage 3: 候选评分
            logger.info("阶段3: 评分候选关系（5维度 + 数据库采样）")
            scored_candidates = self.scorer.score_candidates(candidates, tables)
            logger.info(f"评分完成: {len(scored_candidates)} 个")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "评分样例: %s",
                    [self._format_candidate_debug(c) for c in scored_candidates[:3]],
                )

            # Stage 4: 决策过滤 + 抑制
            logger.info("阶段4: 决策过滤和抑制规则")
            inferred_relations, suppressed, below_threshold = self.decision_engine.filter_and_suppress(
                scored_candidates
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
