"""基于真实产物的 SQL RAG 训练场景测试。

说明：
1. 仅在 tests/ 下实现测试专用编排，不修改正式代码。
2. 生成阶段沿用“按 domain 逐个生成”的正式逻辑，但在 prompt 中额外注入 rel.md 中与当前 domain 表相关的关系段落。
3. 验证与 SQL 修复直接复用正式 SQLValidator。
"""

from __future__ import annotations

import copy
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from contextlib import redirect_stdout

import pytest

from metaweave.core.metadata.connector import DatabaseConnector
from metaweave.core.sql_rag.generator import QuestionSQLGenerator
from metaweave.core.sql_rag.models import GenerationResult, QuestionSQLPair
from metaweave.core.sql_rag.prompts import SYSTEM_PROMPT
from metaweave.core.sql_rag.validator import SQLValidator
from metaweave.services.llm_service import LLMService
from services.config_loader import ConfigLoader


TRAINING_USER_PROMPT_TEMPLATE = """## 数据库背景
{database_description}

## 当前业务主题
主题名称：{domain_name}
主题描述：{domain_description}

## 当前主题包含的表结构文档
{md_content}

## 当前主题相关的表间关系
{rel_content}

## 生成目标
请基于以上资料，生成 {questions_per_domain} 组高质量、可用于训练文本到 SQL 的标准 question/sql 对。

## 训练样本要求
1. 使用 PostgreSQL 语法。
2. 问题使用中文，SQL 中表名和字段名必须使用真实英文名。
3. 查询结果列可使用中文别名，但别名必须用双引号包裹，避免出现 `2021年新建数` 这类未加引号的标识符错误。
4. 生成的样例要有业务代表性，优先覆盖经营分析、趋势分析、排行分析、结构占比、跨表关联分析、明细定位等常见业务场景。
5. 如果表间关系信息中出现了可用关联，请优先参考这些关系设计 JOIN，避免臆造关联字段。
6. 如果关系文档中没有明确给出某些表的关联关系，不要强行 JOIN；宁可生成单表高质量分析 SQL，也不要编造字段。
7. SQL 必须可执行，避免引用不存在的字段、表、别名或聚合错误。
8. 每条 SQL 必须是单行文本，并且以分号结尾。
9. 尽量让不同 SQL 的分析角度不重复，避免只是简单换个筛选条件。
10. 尽量包含真实分析中常见的时间、分组、排序、TOP N、环比/同比替代写法、业务汇总等模式。
11. 所有问题和 SQL 都必须严格基于提供的表结构和关系信息，不要虚构新表、新字段。

## 额外约束
1. 输出严格为 JSON 数组，不要包含解释说明。
2. 每个元素仅包含 `question` 和 `sql` 两个字段。
3. question 与 sql 都不能包含换行符。
4. 如果需要使用中文别名，请统一采用双引号，例如 `AS "服务区名称"`。

## 输出格式
[
  {{"question": "问题文本", "sql": "SELECT ...;"}},
  {{"question": "问题文本", "sql": "SELECT ...;"}}
]"""


@dataclass
class TrainingScenarioResult:
    """测试专用生成结果。"""

    generation: GenerationResult
    prompts: dict[str, str]


class DomainTrainingScenarioGenerator:
    """测试专用 SQL 生成器。

    复用正式 QuestionSQLGenerator 的：
    - db_domains.yaml 读取
    - md 目录读取
    - md 按 domain 表过滤
    - LLM 返回解析与清洗
    """

    def __init__(
        self,
        llm_service: Any,
        generation_config: dict[str, Any],
        rel_dir: Path,
        md_dir: Path,
    ) -> None:
        self._base = QuestionSQLGenerator(llm_service, generation_config)
        self.llm_service = llm_service
        self.rel_dir = Path(rel_dir)
        self.md_dir = Path(md_dir)
        # 仅复用“按表找关系段落”的现有逻辑，不执行校验。
        self._rel_helper = SQLValidator(
            connector=object(),
            config={},
            md_dir=str(md_dir),
            rel_dir=str(rel_dir),
        )

    def generate(
        self,
        domains_config_path: Path,
        output_file: Path,
        questions_per_domain: int = 3,
    ) -> TrainingScenarioResult:
        domains_config = self._base._load_domains_config(str(domains_config_path))
        db_info = domains_config.get("database", {})
        db_name = db_info.get("name", "unknown")
        db_description = db_info.get("description", "")
        domains = domains_config.get("domains", [])
        md_map = self._base._build_md_map(str(self.md_dir))

        pairs: list[QuestionSQLPair] = []
        domain_stats: dict[str, int] = {}
        prompts: dict[str, str] = {}

        for domain in domains:
            domain_name = str(domain.get("name", "")).strip()
            domain_description = str(domain.get("description", "")).strip()
            tables = domain.get("tables", []) or []

            md_content = self._base._build_md_context(tables, md_map)
            rel_content = self._rel_helper._extract_relevant_relationships(tables, db_name)
            if not rel_content.strip():
                rel_content = "（未提取到与当前主题表相关的关系段落，可仅依据表结构生成高质量单表或谨慎关联的 SQL。）"

            prompt = TRAINING_USER_PROMPT_TEMPLATE.format(
                database_description=db_description,
                domain_name=domain_name,
                domain_description=domain_description,
                md_content=md_content,
                rel_content=rel_content,
                questions_per_domain=questions_per_domain,
            )
            prompts[domain_name] = prompt

            response = self.llm_service.call_llm(prompt, system_message=SYSTEM_PROMPT)
            domain_pairs = self._base._parse_and_clean(response)[:questions_per_domain]

            for pair in domain_pairs:
                pair.domain = domain_name
                pair.tables = list(tables)

            pairs.extend(domain_pairs)
            domain_stats[domain_name] = len(domain_pairs)

        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_data = [
            {
                "question": pair.question,
                "sql": pair.sql,
                "domain": pair.domain,
                "tables": pair.tables,
            }
            for pair in pairs
        ]
        output_file.write_text(
            json.dumps(output_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        generation = GenerationResult(
            success=len(pairs) > 0,
            pairs=pairs,
            domain_stats=domain_stats,
            total_generated=len(pairs),
            output_file=str(output_file),
        )
        return TrainingScenarioResult(generation=generation, prompts=prompts)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_main_config() -> dict[str, Any]:
    config_path = _project_root() / "configs" / "metadata_config.yaml"
    with redirect_stdout(io.StringIO()):
        return ConfigLoader(str(config_path)).load()


def _build_training_llm_config(full_config: dict[str, Any]) -> dict[str, Any]:
    llm_config = copy.deepcopy(full_config.get("llm", {}))
    active = llm_config.get("active")
    providers = llm_config.get("providers", {})
    if not active or active not in providers:
        raise ValueError("全局 llm.active/provider 配置无效，无法构造测试 LLM 配置")

    dedicated = full_config.get("domain_generation", {}).get("llm", {}) or {}
    model_name = dedicated.get("model_name")
    if not model_name:
        raise ValueError("domain_generation.llm.model_name 未配置")

    providers[active]["model"] = model_name
    return llm_config


def test_sql_rag_training_scenario_with_rel_context() -> None:
    project_root = _project_root()
    config = _load_main_config()

    domains_path = project_root / "configs" / "db_domains.yaml"
    md_dir = project_root / "output" / "md"
    rel_dir = project_root / "output" / "rel"
    sql_dir = project_root / "output" / "sql"
    output_file = sql_dir / "qs_highway_db_pair_test.json"

    assert domains_path.exists(), f"缺少 domain 配置文件: {domains_path}"
    assert md_dir.exists(), f"缺少 md 目录: {md_dir}"
    assert rel_dir.exists(), f"缺少 rel 目录: {rel_dir}"

    llm_config = _build_training_llm_config(config)
    generation_config = copy.deepcopy(config.get("sql_rag", {}).get("generation", {}))
    generation_config["questions_per_domain"] = 3
    generation_config["uncategorized_questions"] = 3

    llm_service = LLMService(llm_config)
    scenario_generator = DomainTrainingScenarioGenerator(
        llm_service=llm_service,
        generation_config=generation_config,
        rel_dir=rel_dir,
        md_dir=md_dir,
    )

    scenario_result = scenario_generator.generate(
        domains_config_path=domains_path,
        output_file=output_file,
        questions_per_domain=3,
    )

    assert output_file.exists(), "测试 SQL 生成文件未产出"
    assert scenario_result.generation.success, "测试 SQL 生成失败"
    assert scenario_result.generation.total_generated > 0
    assert all(
        count == 3 for count in scenario_result.generation.domain_stats.values()
    ), f"并非每个 domain 都生成了 3 条 SQL: {scenario_result.generation.domain_stats}"

    with open(output_file, "r", encoding="utf-8") as f:
        output_pairs = json.load(f)

    assert output_pairs, "输出文件为空"
    assert all(item["sql"].endswith(";") for item in output_pairs)
    assert all("domain" in item for item in output_pairs)
    assert any(
        "当前主题相关的表间关系" in prompt and "## 当前主题包含的表结构文档" in prompt
        for prompt in scenario_result.prompts.values()
    )

    connector = DatabaseConnector(config.get("database", {}))
    try:
        validator = SQLValidator(
            connector=connector,
            config=config.get("sql_rag", {}).get("validation", {}),
            llm_service=llm_service,
            md_dir=str(md_dir),
            rel_dir=str(rel_dir),
        )
        stats = validator.validate_file(
            input_file=str(output_file),
            enable_repair=True,
        )
    finally:
        connector.close()

    assert stats["total"] == scenario_result.generation.total_generated
    assert stats["valid"] + stats["repair_stats"]["successful"] >= 1
    report_files = sorted(sql_dir.glob("sql_validation_summary_*.log"))
    assert report_files, "未生成 SQL 校验报告"
