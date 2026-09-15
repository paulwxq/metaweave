"""基于全量 JSON 的 LLM 增强处理器

本模块实现了从规则引擎生成的全量 JSON 到 LLM 增强的转换：
1. 表分类覆盖：用 LLM 分类结果覆盖规则引擎结果
2. 注释智能补全：检查并补充缺失的表/字段注释，支持覆盖模式
3. Token 优化：裁剪输入视图、按需调用、分批处理
4. 支持内存文档和兼容文件入口，不访问数据库
"""

import asyncio
import copy
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, List

from metaweave.core.metadata.connector import DatabaseConnector
from metaweave.core.metadata.comment_utils import normalize_comment
from metaweave.core.metadata.generation_config import MetadataGenerationConfig
from metaweave.core.metadata.metadata_document import MetadataDocument
from metaweave.services.llm_service import LLMService
from metaweave.utils.file_utils import atomic_write_json

logger = logging.getLogger("metaweave.json_llm_enhancer")

_ALLOWED_TABLE_CATEGORIES = {"fact", "dim", "bridge", "unknown"}


@dataclass(frozen=True)
class JsonEnhancementResult:
    """单个 JSON 文档的可选 LLM 增强结果。"""

    document: Dict
    success: bool
    llm_called: bool = False
    request_count: int = 0
    generated_comments: int = 0
    object_comment_success_count: int = 0
    object_comment_failure_count: int = 0
    column_comment_success_count: int = 0
    column_comment_failure_count: int = 0
    comment_task_attempted: bool = False
    comment_task_succeeded: bool = False
    classification_task_attempted: bool = False
    classification_task_succeeded: bool = False
    error: Optional[str] = None


class JsonLlmEnhancer:
    """基于全量 JSON 的 LLM 增强处理器

    不访问数据库。新的 JSON 生成流程使用内存文档接口；旧文件入口暂时保留给
    尚未适配的 pipeline 调用方。
    """

    def __init__(
        self,
        config: Dict,
        connector: Optional[DatabaseConnector] = None,
        runtime_override: Optional[Dict] = None,
    ):
        """初始化 LLM 增强处理器

        Args:
            config: 完整配置字典
            connector: 数据库连接器（仅用于传递配置，不实际查库）
            runtime_override: 运行时 LLM 配置覆盖（如 CLI 强制 use_async=False）
        """
        self.config = config
        self.runtime_override = runtime_override
        generation_config = MetadataGenerationConfig.from_config(config)
        comment_config = generation_config.json_comments
        self.comment_generation_enabled = comment_config.llm_enabled
        self.classification_enabled = (
            generation_config.json_table_classification.llm_enabled
        )
        self.comment_language = comment_config.language
        self.overwrite_existing = comment_config.overwrite
        self.max_columns_per_call = comment_config.max_columns_per_call
        self.enable_batch_processing = comment_config.enable_batch_processing
        self.llm_service: Optional[LLMService] = None
        output_config = config.get("output", {}) or {}
        json_options = output_config.get("json_options", {}) or {}
        if not isinstance(json_options, dict):
            raise ValueError("output.json_options 必须是对象")
        self.include_generation_timestamps = json_options.get(
            "include_generation_timestamps",
            True,
        )
        if not isinstance(self.include_generation_timestamps, bool):
            raise ValueError(
                "output.json_options.include_generation_timestamps 必须是布尔值"
            )

        global_langchain = (config.get("llm", {}) or {}).get(
            "langchain_config", {}
        ) or {}
        module_langchain = (
            ((config.get("json_generation", {}) or {}).get("llm", {}) or {}).get(
                "langchain_config", {}
            )
            or {}
        )
        runtime_langchain = (runtime_override or {}).get("langchain_config", {}) or {}
        self.use_async = runtime_langchain.get(
            "use_async",
            module_langchain.get("use_async", global_langchain.get("use_async", False)),
        )

    def _ensure_llm_service(self) -> LLMService:
        """仅在确实存在 LLM 任务时解析模型并初始化服务。"""
        if self.llm_service is None:
            from metaweave.services.llm_config_resolver import (
                resolve_module_llm_config,
            )

            llm_config = resolve_module_llm_config(
                self.config,
                "json_generation.llm",
                runtime_override=self.runtime_override,
            )
            self.llm_service = LLMService(llm_config)
        return self.llm_service

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
            return self._run_async(asyncio.to_thread(self._enhance_file_documents, json_files))
        return self._enhance_file_documents(json_files)

    def _enhance_file_documents(self, json_files: List[Path]) -> int:
        """兼容旧文件入口；核心增强逻辑统一委托给内存文档接口。"""
        enhanced_count = 0
        for json_file in json_files:
            try:
                original = self._load_json(json_file)
                outcome = self.enhance_document(original)
                if outcome.success:
                    if outcome.llm_called or outcome.document != original:
                        atomic_write_json(outcome.document, json_file)
                    if outcome.llm_called:
                        enhanced_count += 1
                else:
                    logger.error("增强失败 %s: %s", json_file.name, outcome.error)
            except Exception as exc:
                logger.error("增强失败 %s: %s", json_file.name, exc, exc_info=True)
        return enhanced_count

    def enhance_document(self, table_json: Dict) -> JsonEnhancementResult:
        """在内存中完成一个规则 JSON 文档的可选 LLM 增强。"""
        MetadataDocument.from_dict(table_json)
        original = copy.deepcopy(table_json)
        original.pop("llm_enhanced_at", None)
        table_name = original["table_info"].get("table_name", "<unknown>")

        self._normalize_document_comments(original)

        comment_needs = self._analyze_comment_needs(original)
        need_comments = self.comment_generation_enabled and (
            comment_needs["need_table_comment"]
            or bool(comment_needs["columns_need_comment"])
        )
        need_classification = self.classification_enabled
        if not need_comments and not need_classification:
            return JsonEnhancementResult(document=original, success=True)

        request_count = 0
        errors: List[str] = []
        try:
            service = self._ensure_llm_service()
        except Exception as exc:
            logger.error("LLM 服务初始化失败 %s: %s", table_name, exc, exc_info=True)
            enhanced = copy.deepcopy(original)
            object_success = object_failure = 0
            column_success = column_failure = 0
            errors = [f"LLM 服务初始化失败: {exc}"]
            if need_comments:
                (
                    object_success,
                    object_failure,
                    column_success,
                    column_failure,
                    comment_errors,
                ) = self._apply_requested_comments(enhanced, {}, comment_needs)
                errors.extend(comment_errors)
            self._finalize_enhanced_document(enhanced)
            return JsonEnhancementResult(
                document=enhanced,
                success=False,
                generated_comments=object_success + column_success,
                object_comment_success_count=object_success,
                object_comment_failure_count=object_failure,
                column_comment_success_count=column_success,
                column_comment_failure_count=column_failure,
                comment_task_attempted=need_comments,
                classification_task_attempted=need_classification,
                error="；".join(errors),
            )
        llm_input = self._build_llm_input_view(original)
        columns = comment_needs["columns_need_comment"]
        batches = [columns]
        if need_comments and columns and len(columns) > self.max_columns_per_call:
            if self.enable_batch_processing:
                batches = [
                    columns[i : i + self.max_columns_per_call]
                    for i in range(0, len(columns), self.max_columns_per_call)
                ]
            else:
                batches = [columns[: self.max_columns_per_call]]
                logger.warning(
                    "列注释任务过多且分批被禁用，仅请求前 %s 个列；其余列计为失败",
                    self.max_columns_per_call,
                )

        first_needs = {
            "need_table_comment": comment_needs["need_table_comment"],
            "columns_need_comment": batches[0],
        }
        if need_comments and need_classification:
            prompt = self._build_combined_prompt(llm_input, first_needs)
        elif need_classification:
            prompt = self._build_classification_only_prompt(llm_input)
        else:
            prompt = self._build_comments_only_prompt(llm_input, first_needs)

        logger.debug("JsonLlmEnhancer 当前 LLM 模型: %s", service.model)

        def call_llm(current_prompt: str, task_label: str) -> Dict:
            nonlocal request_count
            request_count += 1
            try:
                parsed = self._parse_llm_response(
                    service.call_llm(current_prompt), table_name
                )
                if not parsed:
                    errors.append(f"{task_label}: LLM 响应不是有效 JSON 对象")
                return parsed
            except Exception as exc:
                logger.error(
                    "LLM 请求失败 %s (%s): %s",
                    table_name,
                    task_label,
                    exc,
                    exc_info=True,
                )
                errors.append(f"{task_label}: {exc}")
                return {}

        first_result = call_llm(prompt, "首批增强")
        merged_result = dict(first_result)
        merged_column_comments = first_result.get("column_comments")
        if not isinstance(merged_column_comments, dict):
            merged_column_comments = {}
        else:
            merged_column_comments = dict(merged_column_comments)
        merged_result["column_comments"] = merged_column_comments

        if need_comments:
            for batch_number, batch_columns in enumerate(batches[1:], start=2):
                batch_needs = {
                    "need_table_comment": False,
                    "columns_need_comment": batch_columns,
                }
                batch_result = call_llm(
                    self._build_comments_only_prompt(llm_input, batch_needs),
                    f"第 {batch_number} 批字段注释",
                )
                batch_comments = batch_result.get("column_comments")
                if isinstance(batch_comments, dict):
                    merged_column_comments.update(batch_comments)

        enhanced = copy.deepcopy(original)
        classification_succeeded = False
        if need_classification:
            try:
                self._merge_classification_result(enhanced, merged_result)
                classification_succeeded = True
            except Exception as exc:
                errors.append(f"表分类: {exc}")
                logger.warning("LLM 表分类失败 %s: %s", table_name, exc)

        object_success = object_failure = 0
        column_success = column_failure = 0
        if need_comments:
            (
                object_success,
                object_failure,
                column_success,
                column_failure,
                comment_errors,
            ) = self._apply_requested_comments(
                enhanced,
                merged_result,
                comment_needs,
            )
            errors.extend(comment_errors)

        self._finalize_enhanced_document(enhanced)
        for error in errors:
            logger.warning("LLM 增强项失败 %s: %s", table_name, error)

        comment_failures = object_failure + column_failure
        return JsonEnhancementResult(
            document=enhanced,
            success=not errors,
            llm_called=request_count > 0,
            request_count=request_count,
            generated_comments=object_success + column_success,
            object_comment_success_count=object_success,
            object_comment_failure_count=object_failure,
            column_comment_success_count=column_success,
            column_comment_failure_count=column_failure,
            comment_task_attempted=need_comments,
            comment_task_succeeded=need_comments and comment_failures == 0,
            classification_task_attempted=need_classification,
            classification_task_succeeded=classification_succeeded,
            error="；".join(errors) if errors else None,
        )

    @staticmethod
    def _normalize_document_comments(document: Dict) -> None:
        table_info = document.get("table_info", {})
        table_info.pop("comment_original", None)
        table_info.pop("comment_source_original", None)
        table_info["comment"] = normalize_comment(table_info.get("comment"))
        if not table_info["comment"]:
            table_info["comment_source"] = ""
        for column in document.get("column_profiles", {}).values():
            column.pop("comment_original", None)
            column.pop("comment_source_original", None)
            column["comment"] = normalize_comment(column.get("comment"))
            if not column["comment"]:
                column["comment_source"] = ""

    def _apply_requested_comments(
        self,
        enhanced: Dict,
        llm_result: Dict,
        comment_needs: Dict,
    ) -> tuple[int, int, int, int, List[str]]:
        """逐项应用注释结果；缺失或空白响应按失败并置空。"""
        object_success = object_failure = 0
        column_success = column_failure = 0
        errors: List[str] = []

        if comment_needs["need_table_comment"]:
            comment = normalize_comment(llm_result.get("table_comment"))
            if comment:
                enhanced["table_info"]["comment"] = comment
                enhanced["table_info"]["comment_source"] = "llm_generated"
                object_success = 1
            else:
                enhanced["table_info"]["comment"] = ""
                enhanced["table_info"]["comment_source"] = ""
                object_failure = 1
                errors.append("对象注释: LLM 未返回有效内容")

        llm_comments = llm_result.get("column_comments")
        if not isinstance(llm_comments, dict):
            llm_comments = {}
        for column_name in comment_needs["columns_need_comment"]:
            profile = enhanced["column_profiles"][column_name]
            comment = normalize_comment(llm_comments.get(column_name))
            if comment:
                profile["comment"] = comment
                profile["comment_source"] = "llm_generated"
                column_success += 1
            else:
                profile["comment"] = ""
                profile["comment_source"] = ""
                column_failure += 1
                errors.append(f"字段注释 {column_name}: LLM 未返回有效内容")

        return (
            object_success,
            object_failure,
            column_success,
            column_failure,
            errors,
        )

    def _finalize_enhanced_document(self, enhanced: Dict) -> None:
        document = MetadataDocument.from_dict(enhanced)
        enhanced["metadata_version"] = document.version
        enhanced.pop("llm_enhanced_at", None)
        if not self.include_generation_timestamps:
            enhanced.pop("generated_timestamp", None)

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
        """通过统一访问器构建字段级白名单输入。"""
        return MetadataDocument.from_dict(table_json).build_json_llm_input()

    def _simplify_column_profiles(self, column_profiles: Dict) -> Dict:
        """兼容旧的内部调用；不再伪造统计值或透传结构标志。"""
        wrapper = {
            "metadata_version": "3.0",
            "table_info": {},
            "column_profiles": column_profiles,
            "table_profile": {
                "classification_source": "rule",
                "indexes": [],
            },
            "sample_records": {},
        }
        return MetadataDocument.from_dict(wrapper).build_json_llm_input()[
            "column_profiles"
        ]

    def _normalize_sample_records(self, sample_records: Dict) -> Dict:
        """规范化展示样例，不保留可由其他事实派生的重复字段。"""
        if not sample_records:
            return {"sample_method": "none", "records": []}
        records = sample_records.get("records", []) or []
        return {
            "sample_method": sample_records.get("sample_method", "limit"),
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
        need_comments: bool,
        classification_enabled: bool = True,
    ) -> Dict:
        """合并 LLM 结果，并在落盘前完成契约校验。"""
        enhanced = copy.deepcopy(table_json)

        if classification_enabled:
            self._merge_classification_result(enhanced, llm_result)

        if need_comments:
            self._merge_table_comment(enhanced, llm_result)
            self._merge_column_comments(enhanced, llm_result)

        self._normalize_document_comments(enhanced)
        self._finalize_enhanced_document(enhanced)

        return enhanced

    def _merge_classification_result(
        self,
        enhanced: Dict,
        llm_result: Dict,
    ) -> None:
        """校验并合并 LLM 表分类，同时幂等保留原规则分类。"""
        table_name = enhanced["table_info"]["table_name"]
        table_profile = enhanced["table_profile"]
        rule_category = table_profile["table_category"]
        rule_confidence = table_profile.get("confidence")
        rule_inference_basis = table_profile.get("inference_basis", [])

        raw_category = llm_result.get("table_category")
        llm_category = None if raw_category is None else str(raw_category).strip().lower()
        if not llm_category:
            raise ValueError(
                f"LLM 响应缺少 table_category（或为空），表: {table_name}"
            )
        if llm_category not in _ALLOWED_TABLE_CATEGORIES:
            raise ValueError(
                f"LLM 响应 table_category 非法: {raw_category!r}，表: {table_name}"
            )

        reason = str(llm_result.get("reason") or "").strip()
        if not reason:
            raise ValueError(f"LLM 分类响应必须包含非空 reason，表: {table_name}")

        raw_confidence = llm_result.get("confidence", 0.9)
        try:
            llm_confidence = float(raw_confidence)
        except (TypeError, ValueError):
            llm_confidence = 0.9
        llm_confidence = max(0.0, min(1.0, llm_confidence))

        existing_rule = table_profile.get("rule_based_classification")
        if isinstance(existing_rule, dict):
            rule_classification = copy.deepcopy(existing_rule)
        else:
            rule_classification = {
                "table_category": rule_category,
                "confidence": rule_confidence,
                "inference_basis": list(rule_inference_basis),
            }
        table_profile["rule_based_classification"] = rule_classification
        table_profile["classification_source"] = "llm"
        table_profile["classification_reason"] = reason
        table_profile["table_category"] = llm_category
        table_profile["confidence"] = llm_confidence
        table_profile["inference_basis"] = ["llm_inferred"]

    def _merge_table_comment(self, enhanced: Dict, llm_result: Dict):
        """合并表注释"""
        current_comment = normalize_comment(enhanced["table_info"].get("comment"))
        llm_comment = normalize_comment(llm_result.get("table_comment"))

        if not llm_comment:
            return

        if not current_comment:
            # 缺失补全
            enhanced["table_info"]["comment"] = llm_comment
            enhanced["table_info"]["comment_source"] = "llm_generated"
        elif self.overwrite_existing:
            # 覆盖模式直接替换，不在产物中保留旧注释审计副本。
            enhanced["table_info"]["comment"] = llm_comment
            enhanced["table_info"]["comment_source"] = "llm_generated"
            enhanced["table_info"].pop("comment_original", None)
            enhanced["table_info"].pop("comment_source_original", None)

    def _merge_column_comments(self, enhanced: Dict, llm_result: Dict):
        """合并字段注释"""
        llm_comments = llm_result.get("column_comments", {})

        for col_name, col_profile in enhanced["column_profiles"].items():
            if col_name not in llm_comments:
                continue

            current_comment = normalize_comment(col_profile.get("comment"))
            llm_comment = normalize_comment(llm_comments[col_name])

            if not llm_comment:
                continue

            if not current_comment:
                # 缺失补全
                col_profile["comment"] = llm_comment
                col_profile["comment_source"] = "llm_generated"
            elif self.overwrite_existing:
                # 覆盖模式直接替换，不在产物中保留旧注释审计副本。
                col_profile["comment"] = llm_comment
                col_profile["comment_source"] = "llm_generated"
                col_profile.pop("comment_original", None)
                col_profile.pop("comment_source_original", None)

    def _load_json(self, file_path: Path) -> Dict:
        """加载 JSON 文件"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        MetadataDocument.from_dict(data)
        return data

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
        """兼容旧测试/调用点，实际使用共享原子写入工具。"""
        atomic_write_json(data, file_path)

    def _build_combined_prompt(self, llm_input_view: Dict, comment_needs: Dict) -> str:
        """构建组合任务 Prompt（分类 + 注释）"""
        language_req = {
            "zh": "使用中文输出注释",
            "en": "Write comments in English",
            "bilingual": "注释使用双语：中文（English）",
        }.get(self.comment_language, "使用中文输出注释")

        # 构建注释任务描述（明确要生成的列名列表，避免模型擅自扩展）
        comment_tasks = []
        action = "重新生成并覆盖" if self.overwrite_existing else "生成"
        if comment_needs["need_table_comment"]:
            comment_tasks.append(f"- 为表{action}描述性注释（table_comment）")
        if comment_needs["columns_need_comment"]:
            cols_str = "、".join(comment_needs["columns_need_comment"][:10])
            if len(comment_needs["columns_need_comment"]) > 10:
                cols_str += f"等 {len(comment_needs['columns_need_comment'])} 个列"
            comment_tasks.append(f"- 为以下列{action}注释：{cols_str}")
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
- reason：判断理由（必填，简短说明，1-2句话）

## 任务二：{"重新生成并覆盖注释" if self.overwrite_existing else "补全缺失注释"}
{chr(10).join(comment_tasks)}

**重要**：
- 仅为上述明确列出的字段生成注释，不要生成其他字段的注释
- 如果本次没有需要生成列注释的字段，请返回 `"column_comments": {{}}`（空对象）
- 注释应简洁、准确、描述业务含义
- {"请根据结构与样例重新生成，不要照抄输入中的原注释" if self.overwrite_existing else "输入中的已有注释必须保持不变"}
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
        action = "重新生成并覆盖" if self.overwrite_existing else "生成"
        if comment_needs["need_table_comment"]:
            task_items.append(f"1. 为表{action}描述性注释（table_comment）")
        if comment_needs["columns_need_comment"]:
            cols_str = "、".join(comment_needs["columns_need_comment"][:10])
            if len(comment_needs["columns_need_comment"]) > 10:
                cols_str += f"等 {len(comment_needs['columns_need_comment'])} 个列"
            task_items.append(f"2. 为以下列{action}注释：{cols_str}")

        return f"""你是一名数据仓库建模专家，请根据表结构生成注释。

## 表结构
{json.dumps(llm_input_view, ensure_ascii=False, indent=2)}

## 任务
{chr(10).join(task_items)}

**重要**：
- 仅为上述明确列出的字段生成注释，不要生成其他字段的注释
- 如果本次没有需要生成列注释的字段，请返回 `"column_comments": {{}}`（空对象）
- 注释应简洁、准确、描述业务含义
- {"请根据结构与样例重新生成，不要照抄输入中的原注释" if self.overwrite_existing else "输入中的已有注释必须保持不变"}
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
