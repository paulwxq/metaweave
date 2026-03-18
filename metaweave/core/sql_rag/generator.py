"""Question-SQL 生成器

基于 output/md/*.md 和 configs/db_domains.yaml，按主题域调用 LLM 生成 Question-SQL 样例。
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from metaweave.core.sql_rag.models import GenerationResult, QuestionSQLPair
from metaweave.core.sql_rag.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


class QuestionSQLGenerator:
    """Question-SQL 生成器"""

    def __init__(
        self,
        llm_service: Any,
        generation_config: Dict[str, Any],
    ):
        self.llm_service = llm_service
        self.config = generation_config
        self.questions_per_domain = self.config.get("questions_per_domain", 10)
        self.uncategorized_questions = self.config.get("uncategorized_questions", 3)
        self.skip_uncategorized = self.config.get("skip_uncategorized", False)
        self.output_dir = Path(self.config.get("output_dir", "output/sql"))

    def generate(
        self,
        domains_config_path: str,
        md_dir: str,
    ) -> GenerationResult:
        """执行 Question-SQL 生成

        Args:
            domains_config_path: db_domains.yaml 路径
            md_dir: output/md/ 目录路径

        Returns:
            GenerationResult
        """
        # 1. 读取 db_domains.yaml
        domains_config = self._load_domains_config(domains_config_path)
        db_info = domains_config.get("database", {})
        db_name = db_info.get("name", "unknown")
        db_description = db_info.get("description", "")
        domains = domains_config.get("domains", [])

        # 2. 构建 {表名: MD内容} 映射
        md_map = self._build_md_map(md_dir)
        logger.info("加载了 %d 个 MD 文件", len(md_map))

        # 3. 按主题域生成
        all_pairs: List[QuestionSQLPair] = []
        domain_stats: Dict[str, int] = {}

        for domain in domains:
            domain_name = domain.get("name", "")

            # 处理 _未分类_ 域
            if domain_name == "_未分类_":
                if self.skip_uncategorized:
                    logger.info("跳过 _未分类_ 主题域")
                    continue
                questions_count = self.uncategorized_questions
            else:
                questions_count = self.questions_per_domain

            if questions_count <= 0:
                logger.info("跳过主题域 %s（生成数量为 0）", domain_name)
                continue

            try:
                pairs = self._generate_for_domain(
                    db_description=db_description,
                    domain=domain,
                    md_map=md_map,
                    questions_count=questions_count,
                )
                # 注入 domain 元数据
                for pair in pairs:
                    pair.domain = domain_name

                all_pairs.extend(pairs)
                domain_stats[domain_name] = len(pairs)
                logger.info(
                    "主题域 [%s] 生成 %d 条 Question-SQL", domain_name, len(pairs)
                )
            except Exception:
                logger.exception("主题域 [%s] 生成失败，跳过", domain_name)
                domain_stats[domain_name] = 0

        # 4. 写入文件
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_file = self.output_dir / f"qs_{db_name}_pair.json"
        self._write_output(all_pairs, output_file)

        return GenerationResult(
            success=len(all_pairs) > 0,
            pairs=all_pairs,
            domain_stats=domain_stats,
            total_generated=len(all_pairs),
            output_file=str(output_file),
        )

    def _load_domains_config(self, path: str) -> Dict[str, Any]:
        """读取 db_domains.yaml"""
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _build_md_map(self, md_dir: str) -> Dict[str, str]:
        """构建 {表名: MD内容} 映射"""
        md_path = Path(md_dir)
        md_map: Dict[str, str] = {}
        if not md_path.exists():
            logger.warning("MD 目录不存在: %s", md_dir)
            return md_map

        for md_file in md_path.glob("*.md"):
            # 文件名即表名（去掉 .md 后缀）
            table_name = md_file.stem
            md_map[table_name] = md_file.read_text(encoding="utf-8")
        return md_map

    def _generate_for_domain(
        self,
        db_description: str,
        domain: Dict[str, Any],
        md_map: Dict[str, str],
        questions_count: int,
    ) -> List[QuestionSQLPair]:
        """为单个主题域生成 Question-SQL"""
        domain_name = domain.get("name", "")
        domain_description = domain.get("description", "")
        tables = domain.get("tables", [])

        # 构建 MD 上下文
        md_content = self._build_md_context(tables, md_map)
        if not md_content:
            logger.warning("主题域 [%s] 没有找到任何 MD 内容", domain_name)
            return []

        # 构建提示词
        prompt = USER_PROMPT_TEMPLATE.format(
            database_description=db_description,
            domain_name=domain_name,
            domain_description=domain_description,
            md_content=md_content,
            questions_per_domain=questions_count,
        )

        logger.debug(
            "主题域 [%s] LLM 提示词\n"
            "========== SYSTEM PROMPT ==========\n%s\n"
            "========== USER PROMPT ==========\n%s\n"
            "=================================",
            domain_name,
            SYSTEM_PROMPT,
            prompt,
        )

        # 调用 LLM
        response = self.llm_service.call_llm(prompt, system_message=SYSTEM_PROMPT)

        # 解析并清洗
        return self._parse_and_clean(response)

    def _build_md_context(
        self, tables: List[str], md_map: Dict[str, str]
    ) -> str:
        """构建 MD 上下文内容"""
        if not tables:
            # tables 为空时使用全量 MD
            return "\n\n---\n\n".join(md_map.values())

        parts: List[str] = []
        for table_name in tables:
            if table_name in md_map:
                parts.append(md_map[table_name])
            else:
                logger.warning("表 %s 的 MD 文件未找到，跳过", table_name)
        return "\n\n---\n\n".join(parts)

    def _parse_and_clean(self, response: str) -> List[QuestionSQLPair]:
        """解析并清洗 LLM 返回结果"""
        # 提取 JSON（支持 markdown code block 包裹）
        json_str = self._extract_json(response)
        if not json_str:
            logger.warning("无法从 LLM 返回中提取 JSON")
            return []

        try:
            raw_pairs = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("LLM 返回的 JSON 解析失败: %s", json_str[:200])
            return []

        if not isinstance(raw_pairs, list):
            logger.warning("LLM 返回非数组格式")
            return []

        pairs: List[QuestionSQLPair] = []
        for item in raw_pairs:
            if not isinstance(item, dict):
                continue
            question = item.get("question", "").strip()
            sql = item.get("sql", "").strip()

            if not question or not sql:
                continue

            # 折叠多行为单行
            question = " ".join(question.split())
            sql = " ".join(sql.split())

            # 确保 SQL 以分号结尾
            if not sql.endswith(";"):
                sql += ";"

            pairs.append(QuestionSQLPair(question=question, sql=sql))
        return pairs

    def _extract_json(self, text: str) -> Optional[str]:
        """从文本中提取 JSON 数组"""
        # 尝试提取 markdown code block
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 尝试直接找 JSON 数组
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            return match.group(0)

        return None

    def _write_output(
        self, pairs: List[QuestionSQLPair], output_file: Path
    ) -> None:
        """写入 JSON 输出文件（覆盖式）"""
        data = [
            {"question": p.question, "sql": p.sql, "domain": p.domain}
            for p in pairs
        ]
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("写入 %d 条 Question-SQL 到 %s", len(data), output_file)

    def clean_output(self, db_name: str) -> None:
        """清理当前数据库对应的目标样例文件"""
        target = self.output_dir / f"qs_{db_name}_pair.json"
        if target.exists():
            target.unlink()
            logger.info("已删除 %s", target)
