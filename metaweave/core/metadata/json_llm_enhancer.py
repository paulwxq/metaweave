"""基于全量 JSON 的 LLM 增强处理器

本模块实现了从规则引擎生成的全量 JSON 到 LLM 增强的转换：
1. 表分类覆盖：用 LLM 分类结果覆盖规则引擎结果
2. 注释智能补全：检查并补充缺失的表/字段注释，支持覆盖模式
3. Token 优化：裁剪输入视图、按需调用、分批处理
4. 完全基于文件：不访问数据库，所有数据来自 JSON 文件
"""

import asyncio
import copy
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, List

from metaweave.core.metadata.connector import DatabaseConnector
from metaweave.services.cache_service import CacheService
from metaweave.services.llm_service import LLMService
from metaweave.utils.file_utils import get_project_root

logger = logging.getLogger("metaweave.json_llm_enhancer")

_ALLOWED_TABLE_CATEGORIES = {"fact", "dim", "bridge", "unknown"}


class JsonLlmEnhancer:
    """基于全量 JSON 的 LLM 增强处理器

    完全基于文件操作，不访问数据库。读取 --step json 生成的全量 JSON，
    通过 LLM 进行表分类覆盖和注释增强，结果原地写回 JSON 文件。
    """

    def __init__(self, config: Dict, connector: Optional[DatabaseConnector] = None):
        """初始化 LLM 增强处理器

        Args:
            config: 完整配置字典
            connector: 数据库连接器（仅用于传递配置，不实际查库）
        """
        self.config = config
        self.llm_service = LLMService(config.get("llm", {}))

        # 注释生成配置（沿用现有 configs/metadata_config.yaml 的 comment_generation.*）
        comment_config = config.get("comment_generation", {})
        self.comment_generation_enabled = comment_config.get("enabled", True)
        self.comment_language = (comment_config.get("language", "zh") or "zh").strip().lower()
        if self.comment_language in {"zh-cn", "zh_cn"}:
            self.comment_language = "zh"
        if self.comment_language not in {"zh", "en", "bilingual"}:
            logger.warning("无效的 comment_generation.language=%s，回退到 zh", self.comment_language)
            self.comment_language = "zh"
        self.overwrite_existing = comment_config.get("overwrite_existing", False)
        self.max_columns_per_call = comment_config.get("max_columns_per_call", 120)
        self.enable_batch_processing = comment_config.get("enable_batch_processing", True)

        # 注释缓存配置（复用现有 CacheService 与 key 设计）
        # - 表注释：table:<schema>.<table>
        # - 字段注释：columns:<schema>.<table>  (value 为 {col_name: comment})
        self.cache_enabled = comment_config.get("cache_enabled", True)
        cache_file = comment_config.get("cache_file", "cache/comment_cache.json")
        cache_path = Path(cache_file)
        if not cache_path.is_absolute():
            cache_path = get_project_root() / cache_path
        self.cache_service = CacheService(cache_path) if self.cache_enabled else None

        # 异步配置
        langchain_config = config.get("llm", {}).get("langchain_config", {})
        self.use_async = langchain_config.get("use_async", False)

    def enhance_json_directory(self, json_dir: Path):
        """增强整个目录的 JSON 文件（按 *.json 扫描并增强）

        Args:
            json_dir: JSON 文件目录

        Returns:
            增强的文件数量（同步模式返回 int；异步模式可能返回 coroutine）
        """
        json_files = list(json_dir.glob("*.json"))
        return self.enhance_json_files(json_files)

    def enhance_json_files(self, json_files: List[Path]):
        """增强指定的一组 JSON 文件（用于 CLI 精确限定"本次生成的文件列表"）

        Args:
            json_files: JSON 文件路径列表

        Returns:
            int: 增强的文件数量

        Note:
            - use_async=false: 同步执行，直接返回 int
            - use_async=true: 异步执行（在无事件循环环境中通过 asyncio.run 执行）
            - CLI 工具强制使用同步模式以确保简单可靠
        """
        if self.use_async:
            return self._run_async(self._enhance_json_files_async(json_files))
        return self._enhance_json_files_sync(json_files)

    def _enhance_json_files_sync(self, json_files: List[Path]) -> int:
        """同步增强（逐表处理；分类必做，注释按需/分批）"""
        enhanced_count = 0

        for json_file in json_files:
            try:
                table_json = self._load_json(json_file)
                table_name = table_json["table_info"]["table_name"]

                comment_needs = self._analyze_comment_needs(table_json)
                # 先尝试用缓存补齐/覆盖注释，减少 LLM 调用与 token 成本
                comment_needs = self._apply_cached_comments(table_json, comment_needs)
                need_comments = (
                    comment_needs["need_table_comment"]
                    or len(comment_needs["columns_need_comment"]) > 0
                )

                llm_input = self._build_llm_input_view(table_json)

                cols = comment_needs["columns_need_comment"]
                batches = [cols]
                if need_comments and cols and len(cols) > self.max_columns_per_call:
                    if self.enable_batch_processing:
                        batches = [
                            cols[i : i + self.max_columns_per_call]
                            for i in range(0, len(cols), self.max_columns_per_call)
                        ]
                    else:
                        batches = [cols[: self.max_columns_per_call]]
                        logger.warning(
                            "列注释任务过多且分批被禁用，仅处理前 %s 个列",
                            self.max_columns_per_call,
                        )

                if need_comments:
                    first_needs = {
                        "need_table_comment": comment_needs["need_table_comment"],
                        "columns_need_comment": batches[0],
                    }
                    prompt0 = self._build_combined_prompt(llm_input, first_needs)
                else:
                    prompt0 = self._build_classification_only_prompt(llm_input)

                response0 = self.llm_service.call_llm(prompt0)
                llm_result0 = self._parse_llm_response(response0, table_name)

                merged_llm_result = dict(llm_result0 or {})
                merged_llm_result.setdefault("column_comments", {})

                for batch_cols in batches[1:]:
                    batch_needs = {
                        "need_table_comment": False,
                        "columns_need_comment": batch_cols,
                    }
                    prompt_i = self._build_comments_only_prompt(llm_input, batch_needs)
                    response_i = self.llm_service.call_llm(prompt_i)
                    llm_result_i = self._parse_llm_response(response_i, table_name)
                    if llm_result_i and isinstance(llm_result_i.get("column_comments"), dict):
                        merged_llm_result["column_comments"].update(llm_result_i["column_comments"])

                enhanced = self._merge_llm_result(table_json, merged_llm_result, need_comments)
                self._atomic_write_json(json_file, enhanced)
                self._update_comment_cache(enhanced, merged_llm_result, need_comments)
                enhanced_count += 1
            except Exception as e:
                logger.error("增强失败 %s: %s", json_file.name, e, exc_info=True)

        logger.info("JSON 增强完成，共 %s 个文件", enhanced_count)
        return enhanced_count

    async def _enhance_json_files_async(self, json_files: List[Path]) -> int:
        """异步增强（批量并发；分类必做，注释按需/分批）"""
        jobs = []

        for table_idx, json_file in enumerate(json_files):
            try:
                table_json = self._load_json(json_file)
                table_name = table_json["table_info"]["table_name"]

                comment_needs = self._analyze_comment_needs(table_json)
                # 缓存应用在异步模式下也执行（但不能并发写缓存文件）
                comment_needs = self._apply_cached_comments(table_json, comment_needs)
                need_comments = (
                    comment_needs["need_table_comment"]
                    or len(comment_needs["columns_need_comment"]) > 0
                )

                llm_input = self._build_llm_input_view(table_json)

                cols = comment_needs["columns_need_comment"]
                batches = [cols]
                if need_comments and cols and len(cols) > self.max_columns_per_call:
                    if self.enable_batch_processing:
                        batches = [
                            cols[i : i + self.max_columns_per_call]
                            for i in range(0, len(cols), self.max_columns_per_call)
                        ]
                    else:
                        batches = [cols[: self.max_columns_per_call]]
                        logger.warning(
                            "列注释任务过多且分批被禁用，仅处理前 %s 个列",
                            self.max_columns_per_call,
                        )

                if need_comments:
                    first_needs = {
                        "need_table_comment": comment_needs["need_table_comment"],
                        "columns_need_comment": batches[0],
                    }
                    prompt0 = self._build_combined_prompt(llm_input, first_needs)
                else:
                    prompt0 = self._build_classification_only_prompt(llm_input)

                jobs.append(
                    {
                        "table_idx": table_idx,
                        "batch_idx": 0,
                        "file": json_file,
                        "table_json": table_json,
                        "table_name": table_name,
                        "prompt": prompt0,
                        "need_comments": need_comments,
                    }
                )

                for b, batch_cols in enumerate(batches[1:], start=1):
                    batch_needs = {
                        "need_table_comment": False,
                        "columns_need_comment": batch_cols,
                    }
                    prompt_i = self._build_comments_only_prompt(llm_input, batch_needs)
                    jobs.append(
                        {
                            "table_idx": table_idx,
                            "batch_idx": b,
                            "file": json_file,
                            "table_json": table_json,
                            "table_name": table_name,
                            "prompt": prompt_i,
                            "need_comments": True,
                        }
                    )
            except Exception as e:
                logger.error("加载失败 %s: %s", json_file.name, e, exc_info=True)

        if not jobs:
            logger.info("未发现可增强的 JSON 文件（或均加载失败）")
            return 0

        prompts = [job["prompt"] for job in jobs]

        def on_progress(done: int, total: int):
            if total:
                logger.info("LLM 增强进度: %s/%s", done, total)

        results = await self.llm_service.batch_call_llm_async(prompts, on_progress=on_progress)
        # 约定：LLMService.batch_call_llm_async 返回 List[Tuple[int, str]]，
        # 其中 int 是 prompts 的原始下标，str 是对应响应；并且内部会按下标排序返回。
        result_map = {idx: response for idx, response in results}

        grouped: Dict[int, List[tuple]] = {}
        for prompt_idx, job in enumerate(jobs):
            resp = result_map.get(prompt_idx, "")
            grouped.setdefault(job["table_idx"], []).append((job["batch_idx"], resp))

        enhanced_count = 0
        for table_idx, batch_responses in grouped.items():
            base_job = next(
                j for j in jobs if j["table_idx"] == table_idx and j["batch_idx"] == 0
            )
            try:
                batch_responses.sort(key=lambda x: x[0])
                llm_result0 = self._parse_llm_response(batch_responses[0][1], base_job["table_name"])

                merged_llm_result = dict(llm_result0 or {})
                merged_llm_result.setdefault("column_comments", {})

                for _, resp in batch_responses[1:]:
                    llm_result_i = self._parse_llm_response(resp, base_job["table_name"])
                    if llm_result_i and isinstance(llm_result_i.get("column_comments"), dict):
                        merged_llm_result["column_comments"].update(llm_result_i["column_comments"])

                enhanced = self._merge_llm_result(
                    base_job["table_json"],
                    merged_llm_result,
                    base_job["need_comments"],
                )
                self._atomic_write_json(base_job["file"], enhanced)
                # 缓存写入时机：异步批次全部返回后，在"合并并落盘 JSON"成功后按表顺序写缓存
                # 这样避免并发写同一个 cache_file 产生竞争/损坏，同时保证缓存与落盘 JSON 尽量一致。
                self._update_comment_cache(enhanced, merged_llm_result, base_job["need_comments"])
                enhanced_count += 1
            except Exception as e:
                logger.error("合并写入失败 %s: %s", base_job["file"].name, e, exc_info=True)

        logger.info("JSON 异步增强完成，共 %s 个文件", enhanced_count)
        return enhanced_count

    def _run_async(self, coro):
        """在无事件循环环境中执行协程

        Note:
            - 无事件循环：使用 asyncio.run() 执行并返回结果
            - 有事件循环：返回 coroutine（调用方需自行处理）
            - CLI 工具已强制使用同步模式，通常不会触发此方法
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        return coro

    def _apply_cached_comments(self, table_json: Dict, comment_needs: Dict) -> Dict:
        """用缓存补齐/覆盖注释（命中则直接写回 table_json 并更新待生成列表）"""
        if (not self.cache_enabled) or (self.cache_service is None) or (not self.comment_generation_enabled):
            return comment_needs

        table_info = table_json.get("table_info", {}) or {}
        schema = table_info.get("schema_name", "")
        table = table_info.get("table_name", "")

        # 1) 表注释缓存
        if comment_needs.get("need_table_comment"):
            cache_key = f"table:{schema}.{table}"
            cached = self.cache_service.get(cache_key)
            if cached and str(cached).strip():
                table_info["comment"] = cached
                table_info["comment_source"] = "llm_generated"
                comment_needs["need_table_comment"] = False

        # 2) 字段注释缓存（整表 dict）
        cols_need = list(comment_needs.get("columns_need_comment", []) or [])
        if cols_need:
            cache_key = f"columns:{schema}.{table}"
            cached_map = self.cache_service.get(cache_key)
            if isinstance(cached_map, dict) and cached_map:
                column_profiles = table_json.get("column_profiles", {}) or {}
                remaining = []
                for col_name in cols_need:
                    cached_comment = cached_map.get(col_name)
                    if cached_comment and str(cached_comment).strip() and col_name in column_profiles:
                        column_profiles[col_name]["comment"] = cached_comment
                        column_profiles[col_name]["comment_source"] = "llm_generated"
                    else:
                        remaining.append(col_name)
                comment_needs["columns_need_comment"] = remaining

        return comment_needs

    def _update_comment_cache(self, enhanced_json: Dict, llm_result: Dict, need_comments: bool) -> None:
        """将本次 LLM 生成/覆盖的注释写回缓存（按表写入）"""
        if (not need_comments) or (not self.cache_enabled) or (self.cache_service is None):
            return

        table_info = enhanced_json.get("table_info", {}) or {}
        schema = table_info.get("schema_name", "")
        table = table_info.get("table_name", "")
        if not schema or not table:
            return

        # 1) 表注释缓存：以最终写入 JSON 的 comment 为准（为空则不写）
        table_comment = (table_info.get("comment") or "").strip()
        if table_comment:
            self.cache_service.set(f"table:{schema}.{table}", table_comment)

        # 2) 字段注释缓存：合并写回整表 dict（避免覆盖掉历史已有列）
        col_comments = llm_result.get("column_comments", {}) or {}
        if isinstance(col_comments, dict) and col_comments:
            key = f"columns:{schema}.{table}"
            existing = self.cache_service.get(key) if self.cache_service else None
            merged = existing if isinstance(existing, dict) else {}
            merged.update({k: v for k, v in col_comments.items() if v and str(v).strip()})
            self.cache_service.set(key, merged)

    def _analyze_comment_needs(self, table_json: Dict) -> Dict:
        """分析哪些注释需要生成（返回明确的字段列表，Token 优化）"""
        if not self.comment_generation_enabled:
            return {
                "need_table_comment": False,
                "columns_need_comment": [],
            }

        table_info = table_json.get("table_info", {})
        column_profiles = table_json.get("column_profiles", {})

        # 判断表注释是否需要生成
        table_comment = (table_info.get("comment") or "").strip()
        need_table_comment = (not table_comment) or self.overwrite_existing

        # 判断哪些列注释需要生成（返回明确的列名列表）
        columns_need_comment = []
        for col_name, col_data in column_profiles.items():
            col_comment = (col_data.get("comment") or "").strip()
            if (not col_comment) or self.overwrite_existing:
                columns_need_comment.append(col_name)

        return {
            "need_table_comment": need_table_comment,
            "columns_need_comment": columns_need_comment,  # 明确的列名列表
        }

    def _build_llm_input_view(self, table_json: Dict) -> Dict:
        """构建 LLM 输入视图（Token 优化裁剪）

        最小改动版裁剪策略：
        - 只提供 LLM 做判断真正需要的"事实类信息"
        - 明确不传入规则推断/采样推断结论字段（减少噪声与误导）
        """
        # 防御式访问所有字段
        table_info = table_json.get("table_info", {})
        column_profiles = table_json.get("column_profiles", {})
        sample_records = table_json.get("sample_records", {})
        table_profile = table_json.get("table_profile", {})

        return {
            "table_info": {
                "schema_name": table_info.get("schema_name", ""),
                "table_name": table_info.get("table_name", ""),
                "comment": table_info.get("comment", ""),
            },
            "column_profiles": self._simplify_column_profiles(column_profiles),
            # 直接复用 json 文件中的 sample_records（不做二次行/列截断）
            "sample_records": self._normalize_sample_records(sample_records),
            "physical_constraints": table_profile.get("physical_constraints", {
                "primary_key": None,
                "foreign_keys": [],
                "unique_constraints": [],
                "indexes": []
            }),
        }

    def _simplify_column_profiles(self, column_profiles: Dict) -> Dict:
        """简化列画像（保留 LLM 需要的关键字段）"""
        simplified = {}
        for col_name, col_data in column_profiles.items():
            # 防御式访问 statistics（可能为 None 或缺失）
            original_stats = col_data.get("statistics") or {}

            simplified[col_name] = {
                "column_name": col_data.get("column_name", col_name),
                "data_type": col_data.get("data_type", "unknown"),
                "is_nullable": col_data.get("is_nullable", True),
                "comment": col_data.get("comment", ""),
                "statistics": {
                    "sample_count": original_stats.get("sample_count", 0),
                    "unique_count": original_stats.get("unique_count", 0),
                    "null_rate": original_stats.get("null_rate", 0.0),
                    "uniqueness": original_stats.get("uniqueness", 0.0),
                    "value_distribution": self._limit_value_distribution(
                        original_stats.get("value_distribution", {})
                    ),
                },
                "structure_flags": col_data.get("structure_flags", {}),
            }
        return simplified

    def _normalize_sample_records(self, sample_records: Dict) -> Dict:
        """规范化 sample_records（仅做缺省填充，不做行/列截断）"""
        if not sample_records:
            return {"sample_method": "none", "sample_size": 0, "total_rows": 0, "records": []}
        records = sample_records.get("records", []) or []
        return {
            "sample_method": sample_records.get("sample_method", "random"),
            "sample_size": sample_records.get("sample_size", len(records)),
            "total_rows": sample_records.get("total_rows", 0),
            "sampled_at": sample_records.get("sampled_at"),
            "records": records,
        }

    def _limit_value_distribution(self, value_dist: Dict, top_k: int = 10) -> Dict:
        """限制值分布的条目数（防止过大）"""
        if not value_dist:
            return {}

        # 按频次排序，保留 top_k
        sorted_items = sorted(value_dist.items(), key=lambda x: x[1], reverse=True)
        return dict(sorted_items[:top_k])

    def _merge_llm_result(
        self,
        table_json: Dict,
        llm_result: Dict,
        need_comments: bool
    ) -> Dict:
        """合并 LLM 结果到全量 JSON（按需合并）"""
        enhanced = copy.deepcopy(table_json)

        # 1. 表类型覆盖策略（固定执行：每表必调 LLM 分类并覆盖，含 unknown）
        rule_category = enhanced["table_profile"]["table_category"]
        rule_confidence = enhanced["table_profile"].get("confidence")
        rule_inference_basis = enhanced["table_profile"].get("inference_basis", [])

        raw_category = llm_result.get("table_category", None)
        llm_category = None if raw_category is None else str(raw_category).strip().lower()
        if not llm_category:
            # 视为异常响应：不做任何覆盖，让上层捕获并避免落盘覆盖 JSON
            raise ValueError(
                f"LLM 响应缺少 table_category（或为空），表: {enhanced['table_info']['table_name']}"
            )
        if llm_category not in _ALLOWED_TABLE_CATEGORIES:
            raise ValueError(
                f"LLM 响应 table_category 非法: {raw_category!r}，表: {enhanced['table_info']['table_name']}"
            )

        raw_confidence = llm_result.get("confidence", 0.9)
        try:
            llm_confidence = float(raw_confidence)
        except Exception:
            llm_confidence = 0.9
        llm_confidence = max(0.0, min(1.0, llm_confidence))

        logger.debug("表 %s LLM reason: %s", enhanced["table_info"]["table_name"], llm_result.get("reason", ""))

        category_changed = (llm_category != rule_category)
        if category_changed:
            logger.warning(
                "表 %s 分类不一致: 规则=%s(%.2f) vs LLM=%s(%.2f) - 采用LLM结果（含unknown）",
                enhanced["table_info"]["table_name"],
                rule_category, rule_confidence or 0,
                llm_category, llm_confidence
            )
        else:
            logger.info(
                "表 %s 分类一致: %s - 更新为LLM的confidence(%.2f)",
                enhanced["table_info"]["table_name"],
                llm_category, llm_confidence
            )

        # 备份规则引擎结果（无论是否一致，都备份）
        enhanced["table_profile"]["table_category_rule_based"] = rule_category
        enhanced["table_profile"]["confidence_rule_based"] = rule_confidence
        enhanced["table_profile"]["inference_basis_rule_based"] = rule_inference_basis

        # 覆盖为 LLM 结果（无论是否一致，都覆盖；llm_category=unknown 也覆盖）
        enhanced["table_profile"]["table_category"] = llm_category
        enhanced["table_profile"]["confidence"] = llm_confidence
        enhanced["table_profile"]["inference_basis"] = ["llm_inferred"]

        # 2. 注释增强（仅当调用了注释任务时执行）
        if need_comments:
            self._merge_table_comment(enhanced, llm_result)
            self._merge_column_comments(enhanced, llm_result)

        # 3. 更新元数据
        # - 保留 json 步骤写入的 generated_at（避免改写"生成时间"的语义）
        # - 新增 llm_enhanced_at 记录增强时间（便于追溯）
        # metadata_version 是"元数据 JSON 的输出 schema 版本号"，由 Step json 的 TableMetadata.to_dict() 统一写入。
        # JsonLlmEnhancer 不负责版本升级：这里只做透传；若历史文件缺失该字段，才回退到当前 schema 版本 2.0。
        enhanced["metadata_version"] = table_json.get("metadata_version", "2.0")
        enhanced["llm_enhanced_at"] = datetime.now(timezone.utc).isoformat()

        return enhanced

    def _merge_table_comment(self, enhanced: Dict, llm_result: Dict):
        """合并表注释"""
        current_comment = enhanced["table_info"].get("comment", "")
        llm_comment = llm_result.get("table_comment")

        if not llm_comment:
            return

        if not current_comment or current_comment.strip() == "":
            # 缺失补全
            enhanced["table_info"]["comment"] = llm_comment
            enhanced["table_info"]["comment_source"] = "llm_generated"
        elif self.overwrite_existing:
            # 覆盖模式（仅首次备份，保证幂等性）
            if "comment_original" not in enhanced["table_info"]:
                enhanced["table_info"]["comment_original"] = current_comment
                enhanced["table_info"]["comment_source_original"] = enhanced["table_info"].get("comment_source", "")
            enhanced["table_info"]["comment"] = llm_comment
            enhanced["table_info"]["comment_source"] = "llm_generated"

    def _merge_column_comments(self, enhanced: Dict, llm_result: Dict):
        """合并字段注释"""
        llm_comments = llm_result.get("column_comments", {})

        for col_name, col_profile in enhanced["column_profiles"].items():
            if col_name not in llm_comments:
                continue

            current_comment = col_profile.get("comment", "")
            llm_comment = llm_comments[col_name]

            if not current_comment or current_comment.strip() == "":
                # 缺失补全
                col_profile["comment"] = llm_comment
                col_profile["comment_source"] = "llm_generated"
            elif self.overwrite_existing:
                # 覆盖模式（仅首次备份，保证幂等性）
                if "comment_original" not in col_profile:
                    col_profile["comment_original"] = current_comment
                    col_profile["comment_source_original"] = col_profile.get("comment_source", "")
                col_profile["comment"] = llm_comment
                col_profile["comment_source"] = "llm_generated"

    def _load_json(self, file_path: Path) -> Dict:
        """加载 JSON 文件"""
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _parse_llm_response(self, response: str, table_name: str) -> Dict:
        """解析 LLM 响应（更健壮的 JSON 提取）"""
        try:
            import re
            cleaned = (response or "").strip()

            # 移除开头的 ```json 或 ```
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.MULTILINE)
            # 移除结尾的 ```
            cleaned = re.sub(r'\s*```\s*$', '', cleaned, flags=re.MULTILINE).strip()

            # 选择第一个 JSON 起始符号（{ 或 [）
            start_candidates = [idx for idx in (cleaned.find("{"), cleaned.find("[")) if idx != -1]
            if not start_candidates:
                # DEBUG 模式：完整输出；其他模式：截断到 2000 字符
                response_log = cleaned if logger.isEnabledFor(logging.DEBUG) else cleaned[:2000]
                logger.error("LLM 响应未找到 JSON 起始符号 (表: %s): %s", table_name, response_log)
                return {}

            start_idx = min(start_candidates)

            # 使用 JSONDecoder.raw_decode：能正确处理字符串中的 { }、转义字符等
            decoder = json.JSONDecoder()
            parsed, _end = decoder.raw_decode(cleaned[start_idx:])

            # 兼容：返回列表时取第一个对象
            if isinstance(parsed, list) and parsed:
                parsed = parsed[0]

            if not isinstance(parsed, dict):
                logger.error("LLM 响应 JSON 非对象 (表: %s): %s", table_name, type(parsed).__name__)
                return {}

            return parsed
        except json.JSONDecodeError as e:
            # DEBUG 模式：完整输出；其他模式：截断到 2000 字符
            response_log = response if logger.isEnabledFor(logging.DEBUG) else response[:2000]
            logger.error("解析 LLM 响应失败 (表: %s): %s\n响应内容: %s", table_name, e, response_log)
            return {}

    def _atomic_write_json(self, file_path: Path, data: Dict):
        """原子写入 JSON（先写临时文件再替换）"""
        temp_file = file_path.with_suffix(".tmp")
        # 1) 先写临时文件（写失败才清理 temp）
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            if temp_file.exists():
                temp_file.unlink()
            raise

        # 2) 再原子替换（replace 失败时：原文件仍保持不变；temp 保留便于排查）
        try:
            os.replace(temp_file, file_path)
        except Exception:
            logger.error("原子替换失败，保留临时文件以便排查: %s", temp_file)
            raise

    def _build_combined_prompt(self, llm_input_view: Dict, comment_needs: Dict) -> str:
        """构建组合任务 Prompt（分类 + 注释）"""
        language_req = {
            "zh": "使用中文输出注释",
            "en": "Write comments in English",
            "bilingual": "注释使用双语：中文（English）",
        }.get(self.comment_language, "使用中文输出注释")

        # 构建注释任务描述（明确要生成的列名列表，避免模型擅自扩展）
        comment_tasks = []
        if comment_needs["need_table_comment"]:
            comment_tasks.append("- 为表生成描述性注释（table_comment）")
        if comment_needs["columns_need_comment"]:
            cols_str = "、".join(comment_needs["columns_need_comment"][:10])
            if len(comment_needs["columns_need_comment"]) > 10:
                cols_str += f"等 {len(comment_needs['columns_need_comment'])} 个列"
            comment_tasks.append(f"- 为以下列生成注释：{cols_str}")
            comment_tasks.append("- column_comments 只能包含上述列名，不得生成其他列的注释")

        return f"""你是一名数据仓库建模专家，请根据我提供的"表结构"和"样例数据"完成任务。

## 表结构与样例数据
{json.dumps(llm_input_view, ensure_ascii=False, indent=2)}

注意：
1) 请仅基于我提供的表结构与样例数据判断，不要自行假设未提供的字段或结论。
2) 请重点参考 sample_records（样例值域）与 physical_constraints（物理约束）进行判断与推理。

## 任务一：判断表的类型（table_category）
1) fact：事实类表，特征：有度量值、随业务增长、含多维度外键
2) dim：维度类表，特征：描述性字段多、较稳定、以ID标识实体
3) bridge：桥接表，特征：用于多对多关系，通常只包含外键
4) unknown：无法判断时选择，不要强行猜测

请给出：
- table_category：表类型（fact/dim/bridge/unknown）
- confidence：置信度（0-1之间的小数）
- reason：判断理由（简短说明，1-2句话，可选，仅用于日志记录）

## 任务二：生成缺失的注释
{chr(10).join(comment_tasks)}

**重要**：
- 仅为上述明确列出的字段生成注释，不要生成其他字段的注释
- 如果本次没有需要生成列注释的字段，请返回 `"column_comments": {{}}`（空对象）
- 注释应简洁、准确、描述业务含义
- {language_req}

## 输出格式（JSON）
{{
  "table_category": "<fact|dim|bridge|unknown>",
  "confidence": 0.95,
  "reason": "判断理由",
  "table_comment": "表的业务含义（仅当任务二需要时）",
  "column_comments": {{
    "<col_name>": "列注释"
  }}
}}

请只返回 JSON，不要包含其他内容。
"""

    def _build_classification_only_prompt(self, llm_input_view: Dict) -> str:
        """构建仅分类任务 Prompt（Token 优化）"""
        return f"""你是一名数据仓库建模专家，请根据我提供的表结构判断表的类型。

## 表结构
{json.dumps(llm_input_view, ensure_ascii=False, indent=2)}

注意：
1) 请仅基于我提供的表结构与样例数据判断，不要自行假设未提供的字段或结论。
2) 请重点参考 sample_records（样例值域）与 physical_constraints（物理约束）进行判断

## 任务：判断表的类型（table_category）
1) fact：事实类表，特征：有度量值、随业务增长、含多维度外键
2) dim：维度类表，特征：描述性字段多、较稳定、以ID标识实体
3) bridge：桥接表，特征：用于多对多关系，通常只包含外键
4) unknown：无法判断时选择，不要强行猜测

## 输出格式（JSON）
{{
  "table_category": "<fact|dim|bridge|unknown>",
  "confidence": 0.95,
  "reason": "判断理由（1-2句话）"
}}

请只返回 JSON，不要包含其他内容。
"""

    def _build_comments_only_prompt(self, llm_input_view: Dict, comment_needs: Dict) -> str:
        """构建仅注释任务 Prompt（用于分批处理）"""
        language_req = {
            "zh": "使用中文输出注释",
            "en": "Write comments in English",
            "bilingual": "注释使用双语：中文（English）",
        }.get(self.comment_language, "使用中文输出注释")

        # 构建任务描述
        task_items = []
        if comment_needs["need_table_comment"]:
            task_items.append("1. 为表生成描述性注释（table_comment）")
        if comment_needs["columns_need_comment"]:
            cols_str = "、".join(comment_needs["columns_need_comment"][:10])
            if len(comment_needs["columns_need_comment"]) > 10:
                cols_str += f"等 {len(comment_needs['columns_need_comment'])} 个列"
            task_items.append(f"2. 为以下列生成注释：{cols_str}")

        return f"""你是一名数据仓库建模专家，请根据表结构生成注释。

## 表结构
{json.dumps(llm_input_view, ensure_ascii=False, indent=2)}

## 任务
{chr(10).join(task_items)}

**重要**：
- 仅为上述明确列出的字段生成注释，不要生成其他字段的注释
- 如果本次没有需要生成列注释的字段，请返回 `"column_comments": {{}}`（空对象）
- 注释应简洁、准确、描述业务含义
- {language_req}

## 输出格式（JSON）
{{
  "table_comment": "表注释（仅当任务1需要时）",
  "column_comments": {{
    "<col_name>": "列注释"
  }}
}}

请只返回 JSON，不要包含其他内容。
"""
