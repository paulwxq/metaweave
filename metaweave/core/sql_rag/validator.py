"""SQL EXPLAIN 校验器

复用 DatabaseConnector 的连接池，在显式事务内执行 SET LOCAL statement_timeout + EXPLAIN。
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from metaweave.core.sql_rag.models import ValidationResult

logger = logging.getLogger(__name__)

# 可重试的错误关键词
_RETRYABLE_KEYWORDS = ("connection", "network", "timeout", "pool")
_LEGACY_CONFIG_KEYS = {
    "max_retries": "sql_validation_max_retries",
    "readonly_mode": "sql_validation_readonly",
    "max_concurrent": "sql_validation_max_concurrent",
}
_REMOVED_CONFIG_KEYS = {
    "modify_original_file": "enable_sql_repair",
}


class SQLValidator:
    """SQL EXPLAIN 校验器"""

    def __init__(
        self,
        connector: Any,
        config: Dict[str, Any],
        llm_service: Optional[Any] = None,
        md_dir: Optional[str] = None,
        rel_dir: Optional[str] = None,
    ):
        """
        Args:
            connector: DatabaseConnector 实例
            config: validation 配置段
            llm_service: LLMService 实例（SQL 修复时需要）
            md_dir: 表结构 MD 文件目录（修复时提供上下文）
            rel_dir: 表间关系文件目录（修复时提供上下文）
        """
        self.connector = connector
        self.config = config
        self.llm_service = llm_service
        self.md_dir = Path(md_dir) if md_dir else None
        self.rel_dir = Path(rel_dir) if rel_dir else None
        self._validate_config_keys()
        self.max_retries = self.config.get("sql_validation_max_retries", 2)

    def _validate_config_keys(self) -> None:
        legacy_keys = sorted(k for k in _LEGACY_CONFIG_KEYS if k in self.config)
        removed_keys = sorted(k for k in _REMOVED_CONFIG_KEYS if k in self.config)
        if not legacy_keys and not removed_keys:
            return

        messages = []
        if legacy_keys:
            replacements = ", ".join(
                f"{key} -> {_LEGACY_CONFIG_KEYS[key]}" for key in legacy_keys
            )
            messages.append(f"已废弃键名，请改用新键名: {replacements}")
        if removed_keys:
            replacements = ", ".join(
                f"{key}（其功能已合并到 {_REMOVED_CONFIG_KEYS[key]}）"
                for key in removed_keys
            )
            messages.append(f"已删除键名，请改用: {replacements}")

        raise ValueError("validation 配置包含非法键名: " + "；".join(messages))

    def _normalize_sql(self, sql: str) -> str:
        """规范化 SQL：去除首尾空白和尾部分号，拒绝多语句"""
        sql = sql.strip().rstrip(";").strip()
        if not sql:
            raise ValueError("SQL 为空")
        if ";" in sql:
            raise ValueError(
                f"检测到多语句（中间含分号），拒绝校验: {sql[:80]}..."
            )
        return sql

    def validate_sql(self, sql: str) -> ValidationResult:
        """规范化 + 在显式事务内执行 SET LOCAL timeout + EXPLAIN"""
        start_time = time.time()
        timeout = self.config.get("timeout", 30)
        retry_count = 0

        for attempt in range(1 + self.max_retries):
            try:
                normalized = self._normalize_sql(sql)
                readonly = self.config.get("sql_validation_readonly", True)
                with self.connector.get_connection() as conn:
                    conn.autocommit = False
                    try:
                        with conn.transaction():
                            with conn.cursor() as cur:
                                cur.execute(
                                    f"SET LOCAL statement_timeout = {timeout * 1000}"
                                )
                                if readonly:
                                    cur.execute(
                                        "SET LOCAL default_transaction_read_only = on"
                                    )
                                cur.execute(f"EXPLAIN {normalized}")
                                cur.fetchall()
                    finally:
                        conn.autocommit = True

                execution_time = time.time() - start_time
                return ValidationResult(
                    sql=normalized,
                    valid=True,
                    execution_time=execution_time,
                    retry_count=retry_count,
                )
            except Exception as e:
                error_msg = str(e).lower()
                if attempt < self.max_retries and self._should_retry(error_msg):
                    retry_count += 1
                    logger.warning(
                        "SQL 校验重试 %d/%d: %s",
                        retry_count,
                        self.max_retries,
                        str(e)[:100],
                    )
                    continue

                execution_time = time.time() - start_time
                return ValidationResult(
                    sql=sql.strip(),
                    valid=False,
                    error_message=str(e),
                    execution_time=execution_time,
                    retry_count=retry_count,
                )

        # 不应到达这里，但以防万一
        execution_time = time.time() - start_time
        return ValidationResult(
            sql=sql.strip(),
            valid=False,
            error_message="超过最大重试次数",
            execution_time=execution_time,
            retry_count=retry_count,
        )

    def _should_retry(self, error_msg: str) -> bool:
        """判断错误是否可重试"""
        return any(kw in error_msg for kw in _RETRYABLE_KEYWORDS)

    def validate_batch(self, sqls: List[str]) -> List[ValidationResult]:
        """并发批量校验"""
        max_concurrent = self.config.get("sql_validation_max_concurrent", 5)
        pool_max = (
            self.connector.pool.max_size
            if self.connector.pool
            else max_concurrent
        )
        max_workers = min(max_concurrent, pool_max)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(self.validate_sql, sqls))

        for i, r in enumerate(results):
            r.index = i
        return results

    def validate_file(
        self,
        input_file: str,
        enable_repair: bool = False,
    ) -> Dict[str, Any]:
        """校验 JSON 文件中的所有 SQL

        Args:
            input_file: *_pair.json 文件路径
            enable_repair: 是否启用 LLM SQL 修复

        Returns:
            校验统计结果
        """
        input_path = Path(input_file)
        with open(input_path, "r", encoding="utf-8") as f:
            pairs = json.load(f)

        sqls = [p.get("sql", "") for p in pairs]
        questions = [p.get("question", "") for p in pairs]

        logger.info("开始校验 %d 条 SQL", len(sqls))
        start_time = time.time()
        results = self.validate_batch(sqls)
        total_time = time.time() - start_time

        valid_count = sum(1 for r in results if r.valid)
        invalid_count = len(results) - valid_count

        # SQL 修复
        repair_stats = {"attempted": 0, "successful": 0, "failed": 0}
        if enable_repair and invalid_count > 0:
            if not self.llm_service:
                raise ValueError("enable_repair=true 时必须提供 llm_service")
            repair_stats = self._repair_failed_sqls(
                results, questions, pairs, input_file=str(input_path)
            )

        # 启用修复时，回写修复成功的 SQL，并删除修复失败的条目
        repair_apply_stats = {"modified": 0, "deleted": 0, "failed": 0}
        if enable_repair:
            repair_apply_stats = self._apply_repair_results_to_file(
                input_path, results, pairs
            )

        # 生成报告
        report = self._build_report(
            input_file=str(input_path),
            results=results,
            questions=questions,
            total_time=total_time,
            repair_stats=repair_stats,
            repair_apply_stats=repair_apply_stats,
        )
        self._write_report(report, input_path.parent)

        return {
            "total": len(results),
            "valid": valid_count,
            "invalid": invalid_count,
            "success_rate": valid_count / len(results) * 100 if results else 0,
            "total_time": total_time,
            "repair_stats": repair_stats,
            "repair_apply_stats": repair_apply_stats,
        }

    def _repair_failed_sqls(
        self,
        results: List[ValidationResult],
        questions: List[str],
        pairs: List[Dict],
        input_file: str = "",
    ) -> Dict[str, int]:
        """LLM SQL 修复（注入表结构和关系上下文）"""
        from metaweave.core.sql_rag.prompts import (
            SQL_REPAIR_PROMPT_TEMPLATE,
            SQL_REPAIR_SYSTEM_PROMPT,
        )

        batch_size = self.config.get("repair_batch_size", 1)
        db_name = self._extract_db_name(input_file)
        failed_indices = [i for i, r in enumerate(results) if not r.valid]

        stats = {"attempted": len(failed_indices), "successful": 0, "failed": 0}

        for batch_start in range(0, len(failed_indices), batch_size):
            batch_indices = failed_indices[batch_start : batch_start + batch_size]
            failed_info = []
            all_table_mds = []
            all_relationships = []

            for idx in batch_indices:
                sql = pairs[idx].get("sql", "")
                table_names = self._extract_table_names(sql)

                # 加载表结构 MD
                for tname in table_names:
                    md_content = self._load_table_md(tname, db_name)
                    if md_content and md_content not in all_table_mds:
                        all_table_mds.append(md_content)

                # 加载相关关系
                if table_names and db_name:
                    rel_content = self._extract_relevant_relationships(
                        table_names, db_name
                    )
                    if rel_content:
                        all_relationships.append(rel_content)

                failed_info.append(
                    f"索引 {idx}:\n"
                    f"  问题: {questions[idx]}\n"
                    f"  SQL: {sql}\n"
                    f"  错误: {results[idx].error_message}"
                )

            table_context = (
                "\n\n---\n\n".join(all_table_mds)
                if all_table_mds
                else "（无可用表结构文档）"
            )
            rel_context = (
                "\n\n".join(all_relationships)
                if all_relationships
                else "（无可用关系信息）"
            )

            prompt = SQL_REPAIR_PROMPT_TEMPLATE.format(
                failed_sqls="\n\n".join(failed_info),
                table_schemas=table_context,
                table_relationships=rel_context,
            )

            try:
                response = self.llm_service.call_llm(
                    prompt, system_message=SQL_REPAIR_SYSTEM_PROMPT
                )
                repaired = self._parse_repair_response(response)

                for repair_item in repaired:
                    repair_idx = repair_item.get("index", -1)
                    repaired_sql = repair_item.get("sql", "")
                    if repair_idx < 0 or repair_idx >= len(results) or not repaired_sql:
                        continue

                    # 重新校验修复后的 SQL
                    re_result = self.validate_sql(repaired_sql)
                    results[repair_idx].repair_attempted = True

                    if re_result.valid:
                        results[repair_idx].repair_successful = True
                        results[repair_idx].repaired_sql = repaired_sql
                        stats["successful"] += 1
                    else:
                        results[repair_idx].repair_error = re_result.error_message
                        stats["failed"] += 1
                        logger.warning(
                            "SQL 修复后仍然校验失败，放弃修复 [索引=%d]: "
                            "原始错误='%s', 修复后错误='%s'",
                            repair_idx,
                            results[repair_idx].error_message[:100],
                            re_result.error_message[:100],
                        )

            except Exception:
                logger.exception("LLM 修复批次失败")
                for idx in batch_indices:
                    results[idx].repair_attempted = True
                    results[idx].repair_error = "LLM 调用失败"
                stats["failed"] += len(batch_indices)

        # 统计未被修复尝试的
        for idx in failed_indices:
            if not results[idx].repair_attempted:
                stats["failed"] += 1

        return stats

    @staticmethod
    def _extract_table_names(sql: str) -> List[str]:
        """从 SQL 中提取 FROM/JOIN 后的表名"""
        pattern = r"(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_.]*)"
        matches = re.findall(pattern, sql, re.IGNORECASE)
        seen = set()
        tables = []
        for m in matches:
            name = m.strip().lower()
            if name not in seen:
                seen.add(name)
                tables.append(m.strip())
        return tables

    @staticmethod
    def _extract_db_name(input_file: str) -> str:
        """从 qs_{db_name}_pair.json 文件名中提取 db_name"""
        stem = Path(input_file).stem
        if stem.startswith("qs_") and stem.endswith("_pair"):
            return stem[3:-5]
        return ""

    def _load_table_md(
        self, table_name: str, db_name: str, default_schema: str = "public"
    ) -> str:
        """加载表的 MD 文档"""
        if not self.md_dir:
            return ""

        parts = table_name.split(".")
        if len(parts) == 2:
            schema, table = parts
        elif len(parts) == 1:
            schema, table = default_schema, parts[0]
        else:
            return ""

        md_file = self.md_dir / f"{db_name}.{schema}.{table}.md"
        if md_file.exists():
            return md_file.read_text(encoding="utf-8")
        return ""

    def _extract_relevant_relationships(
        self, table_names: List[str], db_name: str
    ) -> str:
        """从 rel.md 中提取涉及指定表的关系段落"""
        if not self.rel_dir:
            return ""

        rel_file = self.rel_dir / f"{db_name}.relationships_global.md"
        if not rel_file.exists():
            return ""

        content = rel_file.read_text(encoding="utf-8")
        lines = content.split("\n")

        # 构建表名集合（纯表名，用于标题行匹配）
        table_set = set()
        for t in table_names:
            table_set.add(t.split(".")[-1].lower())

        relevant_sections = []
        current_section = []
        is_relevant = False

        for line in lines:
            if line.startswith("### "):
                if is_relevant and current_section:
                    relevant_sections.append("\n".join(current_section))
                current_section = [line]
                heading_lower = line.lower()
                is_relevant = any(
                    f".{t}." in heading_lower or heading_lower.endswith(f".{t}")
                    for t in table_set
                )
            else:
                current_section.append(line)

        if is_relevant and current_section:
            relevant_sections.append("\n".join(current_section))

        return "\n\n".join(relevant_sections)

    def _parse_repair_response(self, response: str) -> List[Dict]:
        """解析修复响应"""
        import re

        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", response, re.DOTALL)
        json_str = match.group(1) if match else response

        match = re.search(r"\[.*\]", json_str, re.DOTALL)
        if match:
            json_str = match.group(0)

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("修复响应 JSON 解析失败")
            return []

    def _apply_repair_results_to_file(
        self,
        input_path: Path,
        results: List[ValidationResult],
        pairs: List[Dict],
    ) -> Dict[str, int]:
        """将 SQL 修复结果回写到原文件"""
        stats = {"modified": 0, "deleted": 0, "failed": 0}

        # 备份
        backup_path = input_path.with_suffix(input_path.suffix + ".backup")
        backup_path.write_text(input_path.read_text(encoding="utf-8"), encoding="utf-8")
        logger.info("已备份到 %s", backup_path)

        new_pairs = []
        for i, (result, pair) in enumerate(zip(results, pairs)):
            if result.valid:
                new_pairs.append(pair)
            elif result.repair_successful and result.repaired_sql:
                pair["sql"] = result.repaired_sql
                new_pairs.append(pair)
                stats["modified"] += 1
            else:
                stats["deleted"] += 1

        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(new_pairs, f, ensure_ascii=False, indent=2)

        logger.info(
            "修复结果已回写原文件: 替换 %d 条, 删除 %d 条",
            stats["modified"],
            stats["deleted"],
        )
        return stats

    def _build_report(
        self,
        input_file: str,
        results: List[ValidationResult],
        questions: List[str],
        total_time: float,
        repair_stats: Dict[str, int],
        repair_apply_stats: Dict[str, int],
    ) -> str:
        """构建校验报告"""
        valid_count = sum(1 for r in results if r.valid)
        invalid_count = len(results) - valid_count
        avg_time = (
            sum(r.execution_time for r in results) / len(results) if results else 0
        )
        total_retries = sum(r.retry_count for r in results)
        success_rate = valid_count / len(results) * 100 if results else 0

        lines = [
            "SQL验证报告",
            "=" * 50,
            "",
            f"输入文件: {input_file}",
            f"验证时间: {datetime.now().isoformat()}",
            f"验证耗时: {total_time:.2f}秒",
            "",
            "验证结果摘要:",
            f"  总SQL数量: {len(results)}",
            f"  有效SQL: {valid_count}",
            f"  无效SQL: {invalid_count}",
            f"  成功率: {success_rate:.2f}%",
            f"  平均耗时: {avg_time:.3f}秒",
            f"  重试次数: {total_retries}",
        ]

        if repair_stats["attempted"] > 0:
            repair_rate = (
                repair_stats["successful"] / repair_stats["attempted"] * 100
                if repair_stats["attempted"]
                else 0
            )
            lines.extend([
                "",
                "SQL修复统计:",
                f"  尝试修复: {repair_stats['attempted']}",
                f"  修复成功: {repair_stats['successful']}",
                f"  修复失败: {repair_stats['failed']}",
                f"  修复成功率: {repair_rate:.2f}%",
            ])

        if (
            repair_apply_stats["modified"] > 0
            or repair_apply_stats["deleted"] > 0
        ):
            lines.extend([
                "",
                "修复结果回写统计:",
                f"  替换的SQL: {repair_apply_stats['modified']}",
                f"  删除的无效项: {repair_apply_stats['deleted']}",
                f"  回写失败: {repair_apply_stats['failed']}",
            ])

        # 错误详情
        failed = [
            (i, r)
            for i, r in enumerate(results)
            if not r.valid and not r.repair_successful
        ]
        if failed:
            lines.extend(["", f"错误详情（共{len(failed)}个）:", "=" * 50, ""])
            for seq, (i, r) in enumerate(failed, 1):
                q = questions[i] if i < len(questions) else "N/A"
                lines.extend([
                    f"{seq}. 问题: {q}",
                    f"   错误: {r.error_message}",
                ])
                if r.repair_attempted:
                    lines.append(f"   LLM修复尝试: 失败")
                    if r.repair_error:
                        lines.append(f"   修复失败原因: {r.repair_error}")
                lines.extend([f"   完整SQL:", f"   {r.sql}", "-" * 40, ""])

        # 成功修复的
        repaired = [
            (i, r)
            for i, r in enumerate(results)
            if r.repair_successful
        ]
        if repaired:
            lines.extend(["", f"成功修复的SQL（共{len(repaired)}个）:", "=" * 50, ""])
            for seq, (i, r) in enumerate(repaired, 1):
                q = questions[i] if i < len(questions) else "N/A"
                lines.extend([
                    f"{seq}. 问题: {q}",
                    f"   原始错误: {r.error_message}",
                    f"   修复后SQL:",
                    f"   {r.repaired_sql}",
                    "-" * 40,
                    "",
                ])

        return "\n".join(lines)

    def _write_report(self, report: str, output_dir: Path) -> None:
        """写入校验报告"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = output_dir / f"sql_validation_summary_{timestamp}.log"
        report_file.write_text(report, encoding="utf-8")
        logger.info("校验报告已写入 %s", report_file)
