"""dim_tables.yaml 配置文件生成器。"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from metaweave.core.dim_value.models import DimTablesConfig
from metaweave.utils.file_utils import ensure_dir, load_json

logger = logging.getLogger(__name__)


class DimTableConfigGenerator:
    """dim_tables.yaml 配置文件生成器。

    自动从 json 目录扫描维表（table_category='dim'），
    生成初始配置文件框架，embedding_col 字段留空，由人工填写。
    """

    def __init__(self, json_dir: Path, output_path: Path):
        self.json_dir = Path(json_dir)
        self.output_path = Path(output_path)

    def generate(self) -> Dict[str, Any]:
        """生成配置文件并写入磁盘。

        Returns:
            生成的配置字典，格式：
            {
                "databases": {
                    "database_name": {
                        "tables": {
                            "schema.table": {"embedding_col": None}
                        }
                    }
                }
            }
        """
        dim_tables_by_db = self._scan_dim_tables()
        config: Dict[str, Any] = {
            "databases": {
                db_name: {
                    "tables": {
                        f"{schema}.{table}": {"embedding_col": None}
                        for schema, table in sorted(dim_tables)
                    }
                }
                for db_name, dim_tables in sorted(dim_tables_by_db.items())
            }
        }

        self._write_yaml(config)
        total_tables = sum(len(items) for items in dim_tables_by_db.values())
        logger.info(
            "✅ 已生成 dim_tables.yaml，识别到 %s 个数据库、%s 个维度表",
            len(dim_tables_by_db),
            total_tables,
        )
        return config

    def _scan_dim_tables(self) -> Dict[str, Set[Tuple[str, str]]]:
        """扫描 json 目录，识别 dim 表。"""

        if not self.json_dir.exists():
            logger.warning("json 目录不存在: %s", self.json_dir)
            return {}

        dim_tables_by_db: Dict[str, Set[Tuple[str, str]]] = {}
        json_files = sorted(self.json_dir.glob("*.json"))

        # 实时日志：开始扫描
        logger.info("📋 发现 %d 个 JSON 文件，开始扫描...", len(json_files))

        for idx, path in enumerate(json_files, 1):
            # 实时日志：当前处理的文件
            logger.info("  [%d/%d] 检查: %s", idx, len(json_files), path.name)

            data = load_json(path)
            if not data or not isinstance(data, dict):
                continue

            table_profile = data.get("table_profile") or {}
            if table_profile.get("table_category") != "dim":
                continue

            database, schema, table = self._extract_table_identifiers(data, path)
            if database and schema and table:
                db_name = str(database)
                schema_name = str(schema)
                table_name = str(table)
                dim_tables_by_db.setdefault(db_name, set()).add((schema_name, table_name))
                # 实时日志：识别到维度表
                logger.info("    ✅ 识别为维度表: %s.%s.%s", db_name, schema_name, table_name)

        # 实时日志：扫描完成统计
        logger.info("")
        total_tables = sum(len(items) for items in dim_tables_by_db.values())
        logger.info("📊 扫描完成，共识别到 %d 个数据库、%d 个维度表", len(dim_tables_by_db), total_tables)
        return dim_tables_by_db

    @staticmethod
    def _extract_table_identifiers(data: Dict[str, Any], path: Path) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        table_info = data.get("table_info") or {}
        table_profile = data.get("table_profile") or {}

        database = (
            table_info.get("database")
            or table_profile.get("database")
            or data.get("database")
            or data.get("db_name")
            or DimTableConfigGenerator._infer_database_from_filename(path)
        )
        schema = (
            table_info.get("schema_name")
            or table_profile.get("schema_name")
            or data.get("schema_name")
            or data.get("schema")
        )
        table = (
            table_info.get("table_name")
            or table_profile.get("table_name")
            or data.get("table_name")
            or data.get("name")
        )
        return database, schema, table

    @staticmethod
    def _infer_database_from_filename(path: Path) -> Optional[str]:
        parts = path.stem.split(".")
        if len(parts) >= 3 and parts[0]:
            return parts[0]
        return None

    def _write_yaml(self, config: Dict[str, Any]) -> None:
        """写入 YAML 文件（带简单注释）。"""

        ensure_dir(self.output_path.parent)
        header = (
            "# 维度表加载配置\n"
            "# 说明：此文件由 dim_config --generate 自动生成维表列表（按 database 分组），需人工填写 embedding_col\n"
            "#\n"
            "# embedding_col 支持三种格式：\n"
            "#   1. 单列向量化：embedding_col: column_name\n"
            "#   2. 多列向量化（YAML列表）：embedding_col: [col1, col2, col3]  # 推荐\n"
            "#   3. 多列向量化（逗号分隔）：embedding_col: col1, col2, col3   # 自动拆分\n"
            "#\n"
            "# 示例：\n"
            "# databases:\n"
            "#   your_database:\n"
            "#     tables:\n"
            "#       public.dim_region:\n"
            "#         embedding_col: region_name                   # 单列\n"
            "#       public.dim_store:\n"
            "#         embedding_col: [store_name, address]         # 多列（推荐格式）\n"
            "#       public.dim_product:\n"
            "#         embedding_col: product_name, category, brand # 多列（自动拆分）\n"
            "\n"
        )
        body = yaml.dump(config, allow_unicode=True, default_flow_style=False, sort_keys=False)
        self.output_path.write_text(header + body, encoding="utf-8")

        logger.info("✅ 写入 dim_tables.yaml: %s", self.output_path)


__all__ = ["DimTableConfigGenerator", "DimTablesConfig"]
