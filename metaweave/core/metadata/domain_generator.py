import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from metaweave.services.llm_service import LLMService

logger = logging.getLogger("metaweave.domain_generator")


class LiteralDumper(yaml.SafeDumper):
    """多行字符串使用 | 块标量，提升可读性。"""


def _repr_str(dumper, data):
    style = "|" if isinstance(data, str) and "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


LiteralDumper.add_representer(str, _repr_str)


class DomainGenerator:
    """Domain 列表生成器（基于 MD 摘要 + 可选用户补充说明）。"""

    UNCLASSIFIED_DOMAIN = "_未分类_"
    DEFAULT_MAX_DOMAINS_PER_TABLE = 3

    def __init__(
        self,
        config: Dict,
        yaml_path: str,
        md_context: bool = True,
        md_context_dir: str = None,
        md_context_mode: str = "name_comment",
        md_context_limit: int = 100,
    ):
        self.config = config
        self.yaml_path = Path(yaml_path)
        self.llm_service = LLMService(config.get("llm", {}))
        self.db_config = self._load_yaml()
        self.md_context = md_context
        self.md_context_dir = Path(md_context_dir) if md_context_dir else None
        self.md_context_mode = md_context_mode
        self.md_context_limit = max(1, md_context_limit)

    def _default_config(self) -> Dict[str, Any]:
        return {
            "database": {
                "name": "",
                "description": "",
            },
            "llm_inference": {
                "max_domains_per_table": self.DEFAULT_MAX_DOMAINS_PER_TABLE,
            },
            "domains": [
                {
                    "name": self.UNCLASSIFIED_DOMAIN,
                    "description": "无法归入其他业务主题的表",
                }
            ],
        }

    def _load_yaml(self) -> Dict[str, Any]:
        """加载 db_domains.yaml，不存在时返回默认模板。"""
        if not self.yaml_path.exists():
            logger.info("domains 配置不存在，将使用默认模板初始化: %s", self.yaml_path)
            return self._default_config()

        with open(self.yaml_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"错误：{self.yaml_path} 不是合法的 YAML 对象")
        return loaded

    def generate_from_context(self, user_description: Optional[str] = None) -> Dict[str, Any]:
        """基于 MD 摘要（和可选用户补充说明）生成 database + domains。"""
        if not self.md_context:
            raise ValueError("generate-domains 必须启用 md_context")

        md_summary = self._build_md_context()
        prompt = self._build_prompt(md_summary=md_summary, user_description=user_description)
        logger.debug("Domain generation prompt:\n%s", prompt)

        logger.info("正在调用 LLM 生成 database/domains 配置...")
        response = self.llm_service._call_llm(prompt)
        payload = self._parse_response(response)

        logger.info("成功解析 domains 配置，domain 数量: %s", len(payload.get("domains", [])))
        return payload

    # 兼容旧调用：仍返回 domains 列表
    def generate_from_description(self) -> List[Dict[str, str]]:
        payload = self.generate_from_context(user_description=None)
        return payload.get("domains", [])

    def _build_prompt(self, md_summary: str, user_description: Optional[str]) -> str:
        """根据是否传入用户描述，动态构建提示词。"""
        if user_description and user_description.strip():
            return f"""
你是一个数据库业务分析专家。请根据以下提供的【表结构摘要】（包含表名和首行注释），以及【用户补充说明】，生成该数据库的整体配置信息。

【用户补充说明】
{user_description.strip()}

【表结构摘要】（最多 {self.md_context_limit} 个）
{md_summary}

## 任务
1. 分析这些表的业务范围，并结合用户的补充说明，推断该数据库系统的整体用途。
2. 为该数据库起一个合适的名称（database.name）。
3. 结合用户补充说明和表结构，编写一段详细的数据库范围概述（database.description，不少于50字，这会覆盖用户简述）。
4. 基于上述分析，划分 3-8 个合理的业务主题类别（domains）。

## 注意事项
- 不要生成名为 "_未分类_" 的主题（这是系统预置的特殊主题，会自动添加）
- 只生成有明确业务含义的主题

## 输出格式（严格 JSON）
```json
{{
  "database": {{
    "name": "推断出的系统名称",
    "description": "详细的数据库整体描述..."
  }},
  "domains": [
    {{"name": "主题1", "description": "主题1的职责描述"}},
    {{"name": "主题2", "description": "主题2的职责描述"}}
  ]
}}
```
请只返回 JSON，不要包含其他内容。
"""

        return f"""
你是一个数据库业务分析专家。请根据以下提供的【表结构摘要】（包含表名和首行注释），生成该数据库的整体配置信息。

【表结构摘要】（最多 {self.md_context_limit} 个）
{md_summary}

## 任务
1. 分析这些表的业务范围，推断该数据库系统的整体用途。
2. 为该数据库起一个合适的名称（database.name）。
3. 编写一段详细的数据库范围概述（database.description，不少于50字，说明包含哪些核心数据模块）。
4. 基于上述分析，划分 3-8 个合理的业务主题类别（domains）。

## 注意事项
- 不要生成名为 "_未分类_" 的主题（这是系统预置的特殊主题，会自动添加）
- 只生成有明确业务含义的主题

## 输出格式（严格 JSON）
```json
{{
  "database": {{
    "name": "推断出的系统名称",
    "description": "详细的数据库整体描述..."
  }},
  "domains": [
    {{"name": "主题1", "description": "主题1的职责描述"}},
    {{"name": "主题2", "description": "主题2的职责描述"}}
  ]
}}
```
请只返回 JSON，不要包含其他内容。
"""

    def _build_md_context(self) -> str:
        """读取 md 目录生成摘要，按模式/数量限制。"""
        if not self.md_context_dir:
            raise ValueError("缺少 Markdown 摘要目录，请先运行 `metaweave metadata --step md`")
        if not self.md_context_dir.exists():
            raise FileNotFoundError(
                f"缺少 Markdown 摘要文件，目录不存在: {self.md_context_dir}。"
                "请先运行 `metaweave metadata --step md`"
            )

        md_files = sorted(self.md_context_dir.glob("*.md"))
        if not md_files:
            raise ValueError(
                f"缺少 Markdown 摘要文件，目录为空: {self.md_context_dir}。"
                "请先运行 `metaweave metadata --step md`"
            )

        summaries: List[str] = []
        limit = self.md_context_limit
        max_len_comment = 200
        max_len_full = 2000

        for md_file in md_files[:limit]:
            stem = md_file.stem
            try:
                content = md_file.read_text(encoding="utf-8")
            except Exception as exc:
                logger.warning("读取 md 失败: %s, 错误: %s", md_file, exc)
                continue

            if self.md_context_mode == "name":
                summary = stem
            elif self.md_context_mode == "full":
                text = content.strip()
                if len(text) > max_len_full:
                    text = text[:max_len_full] + "..."
                summary = f"{stem}: {text}"
            else:  # name_comment
                first_line = ""
                for line in content.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("#"):
                        line = line.lstrip("#").strip()
                    first_line = line
                    break
                if not first_line:
                    first_line = "(无描述)"
                if len(first_line) > max_len_comment:
                    first_line = first_line[:max_len_comment] + "..."
                summary = f"{stem}: {first_line}"

            summaries.append(f"- {summary}")

        if not summaries:
            raise ValueError(
                f"md 摘要为空，无法生成 domains: {self.md_context_dir}。"
                "请检查 md 文件内容或重新执行 `metaweave metadata --step md`"
            )

        logger.info("md_context: 已读取 %s 个 md 文件作为摘要（限制 %s）", len(summaries), limit)
        return "\n".join(summaries)

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """解析 LLM 返回的 JSON（兼容 ```json 代码块）。"""
        text = response.strip()
        if text.startswith("```"):
            parts = text.split("```")
            if len(parts) >= 2:
                text = parts[1]
                if text.startswith("json"):
                    text = text[4:]
            text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("LLM 返回格式错误，无法解析 JSON: %s", exc)
            logger.error("原始返回: %s", response)
            raise ValueError("错误：LLM 返回格式错误，无法解析为 JSON，请重试") from exc

        if not isinstance(data, dict):
            raise ValueError("错误：LLM 返回 JSON 顶层必须是对象")

        database = data.get("database", {}) or {}
        if not isinstance(database, dict):
            database = {}
        name = str(database.get("name", "")).strip()
        description = str(database.get("description", "")).strip()
        if not name:
            name = "未命名数据库"
        if not description:
            description = "数据库整体描述由系统自动生成。"

        domains = self._normalize_domains(data.get("domains", []))
        if not domains:
            raise ValueError("LLM 返回的 domains 列表为空")

        return {
            "database": {
                "name": name,
                "description": description,
            },
            "domains": domains,
        }

    def _normalize_domains(self, domains_raw: Any) -> List[Dict[str, str]]:
        if not isinstance(domains_raw, list):
            return []

        normalized: List[Dict[str, str]] = []
        for item in domains_raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            description = str(item.get("description", "")).strip()
            if not name:
                continue
            if not description:
                description = f"{name} 相关业务主题"
            normalized.append({"name": name, "description": description})
        return normalized

    def write_to_yaml(self, generated: Dict[str, Any] | List[Dict[str, str]]) -> List[Dict[str, str]]:
        """将结果写入 YAML 文件，并强制注入固定参数。"""
        if isinstance(generated, list):
            generated = {"domains": generated}
        if not isinstance(generated, dict):
            raise ValueError("write_to_yaml 入参必须是 dict 或 domains 列表")

        database = generated.get("database", {}) or {}
        if not isinstance(database, dict):
            database = {}

        database_name = str(database.get("name", "")).strip()
        database_description = str(database.get("description", "")).strip()

        existing_database = self.db_config.get("database", {}) or {}
        if not isinstance(existing_database, dict):
            existing_database = {}
        if not database_name:
            database_name = str(existing_database.get("name", "")).strip() or "未命名数据库"
        if not database_description:
            database_description = (
                str(existing_database.get("description", "")).strip()
                or "数据库整体描述由系统自动生成。"
            )

        incoming_domains = self._normalize_domains(generated.get("domains", []))
        filtered_domains = [
            d for d in incoming_domains if d.get("name") != self.UNCLASSIFIED_DOMAIN
        ]
        unclassified = {
            "name": self.UNCLASSIFIED_DOMAIN,
            "description": "无法归入其他业务主题的表",
        }
        final_domains = [unclassified] + filtered_domains

        self.db_config["database"] = {
            "name": database_name,
            "description": database_description,
        }
        self.db_config["llm_inference"] = {
            "max_domains_per_table": self.DEFAULT_MAX_DOMAINS_PER_TABLE,
        }
        self.db_config["domains"] = final_domains

        self.yaml_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.yaml_path, "w", encoding="utf-8") as f:
            f.write("# 数据库业务主题配置\n")
            yaml.dump(
                self.db_config,
                f,
                Dumper=LiteralDumper,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

        logger.info(
            "domains 配置已写入 %s（共 %s 个，含 _未分类_）",
            self.yaml_path,
            len(final_domains),
        )
        return final_domains
