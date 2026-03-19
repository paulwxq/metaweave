"""SQL RAG 上下文提取工具"""

import logging
from pathlib import Path
from typing import List, Union

logger = logging.getLogger(__name__)


def extract_relevant_relationship_sections(
    rel_dir: Union[str, Path], table_names: List[str], db_name: str
) -> str:
    """从 rel.md 中提取涉及指定表的关系段落。
    
    匹配逻辑优先使用 schema.table，完全无法匹配时（或只能获取到纯表名时）退化为纯表名点模式匹配。
    
    Args:
        rel_dir: 关系文件存放目录
        table_names: 相关表名列表（支持 db.schema.table, schema.table 或 table 格式）
        db_name: 数据库名（用于构造文件名）
        
    Returns:
        包含所有相关关系的自然语言提示词片段，如无相关关系或文件不存在则返回空字符串。
    """
    if not rel_dir:
        return ""
        
    rel_file = Path(rel_dir) / f"{db_name}.relationships_global.md"
    if not rel_file.exists():
        return ""

    # 解析表名，分离出全限定(schema.table)和纯表名(table)
    qualified_tables = set()
    pure_tables = set()
    
    for t in table_names:
        parts = t.lower().split(".")
        if len(parts) >= 3:
            # db.schema.table -> schema.table
            qualified_tables.add(f"{parts[-2]}.{parts[-1]}")
            pure_tables.add(parts[-1])
        elif len(parts) == 2:
            # schema.table
            qualified_tables.add(t.lower())
            pure_tables.add(parts[-1])
        else:
            # pure table
            pure_tables.add(t.lower())

    content = rel_file.read_text(encoding="utf-8")
    lines = content.split("\n")
    
    # 第一遍：严格使用 schema.table 进行精确匹配
    precise_sections = []
    current_section = []
    is_relevant = False
    
    for line in lines:
        if line.startswith("### "):
            if is_relevant and current_section:
                precise_sections.append("\n".join(current_section))
            current_section = [line]
            heading_lower = line.lower()
            
            # 精确匹配：标题应该形如 schema.table.column -> schema.table.column
            is_relevant = any(
                f"{qt}." in heading_lower
                for qt in qualified_tables
            )
        else:
            if current_section:
                current_section.append(line)
                
    if is_relevant and current_section:
        precise_sections.append("\n".join(current_section))
        
    if precise_sections:
        return "\n\n".join(precise_sections)
        
    # 第二遍：完全脱靶兜底（或仅配置了纯表名导致第一遍无效），退化为纯表名点模式匹配
    fallback_sections = []
    current_section = []
    is_relevant = False
    
    for line in lines:
        if line.startswith("### "):
            if is_relevant and current_section:
                fallback_sections.append("\n".join(current_section))
            current_section = [line]
            heading_lower = line.lower()
            
            # 纯表名兜底匹配：使用原有的点模式 .table. 或 endswith(.table)
            is_relevant = any(
                f".{pt}." in heading_lower or heading_lower.endswith(f".{pt}")
                for pt in pure_tables
            )
        else:
            if current_section:
                current_section.append(line)
                
    if is_relevant and current_section:
        fallback_sections.append("\n".join(current_section))
        
    return "\n\n".join(fallback_sections)
