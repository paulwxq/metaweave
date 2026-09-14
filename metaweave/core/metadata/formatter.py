"""输出格式化器

将元数据格式化为 DDL、Markdown、JSON 等格式并保存。
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import pandas as pd

from metaweave.core.metadata.models import TableMetadata
from metaweave.core.metadata.metadata_document import MetadataDocument
from metaweave.utils.file_utils import atomic_write_json, save_text, ensure_dir
from metaweave.utils.data_utils import dataframe_to_sample_dict, format_data_type

logger = logging.getLogger("metaweave.formatter")


class OutputFormatter:
    """输出格式化器
    
    将表元数据格式化为不同格式并保存到文件。
    """
    
    def __init__(self, config: dict, database_name: str):
        """初始化输出格式化器
        
        Args:
            config: 配置字典
                - output_dir: 输出目录
                - ddl_directory: DDL 输出目录
                - json_directory: JSON 输出目录
                - markdown_directory: Markdown 输出目录
                - formats: 输出格式列表 ['ddl', 'markdown', 'json']
                - ddl_options: DDL 选项
                - markdown_options: Markdown 选项
            database_name: 数据库名称（来自 database.database）
        """
        self.config = config
        self.output_dir = Path(config.get("output_dir", "output"))
        self.formats = config.get("formats", ["ddl", "markdown", "json"])
        self.ddl_options = config.get("ddl_options", {})
        sample_records_config = self.ddl_options.get("sample_records", {})
        sample_record_count = sample_records_config.get("count", 3)
        if isinstance(sample_record_count, bool) or not isinstance(
            sample_record_count,
            int,
        ):
            raise ValueError("output.ddl_options.sample_records.count 必须是非负整数")
        if sample_record_count < 0:
            raise ValueError("output.ddl_options.sample_records.count 必须是非负整数")
        self.sample_record_options = {
            "enabled": sample_records_config.get("enabled", True),
            "count": sample_record_count,
        }
        self.markdown_options = config.get("markdown_options", {})
        json_options = config.get("json_options", {}) or {}
        self.json_options = json_options
        self.include_generation_timestamps = (
            json_options.get("include_generation_timestamps", True)
            if isinstance(json_options, dict)
            else True
        )
        self.markdown_sample_value_count = max(
            1,
            int(self.markdown_options.get("sample_value_count", 2))
        )

        # 1. 确定并确保 DDL 目录存在
        ddl_dir_str = config.get("ddl_directory")
        if ddl_dir_str:
            self.ddl_dir = Path(ddl_dir_str)
            if not self.ddl_dir.is_absolute():
                self.ddl_dir = Path.cwd() / self.ddl_dir
        else:
            self.ddl_dir = self.output_dir / "ddl"
        ensure_dir(self.ddl_dir)

        # 2. 确定并确保 Markdown 目录存在
        md_dir_str = config.get("markdown_directory")
        if md_dir_str:
            self.markdown_dir = Path(md_dir_str)
            if not self.markdown_dir.is_absolute():
                self.markdown_dir = Path.cwd() / self.markdown_dir
        else:
            self.markdown_dir = self.output_dir / "md"
        ensure_dir(self.markdown_dir)

        # 3. 确定并确保 JSON 目录存在
        json_dir_str = config.get("json_directory")
        if json_dir_str:
            self.json_dir = Path(json_dir_str)
            if not self.json_dir.is_absolute():
                self.json_dir = Path.cwd() / self.json_dir
        else:
            self.json_dir = self.output_dir / "json"
        ensure_dir(self.json_dir)
        
        # 数据库名：统一来自 database.database
        self.database_name = database_name
        
        logger.info(f"输出格式化器已初始化. DDL: {self.ddl_dir}, JSON: {self.json_dir}, MD: {self.markdown_dir}")

    def validate_json_options(self) -> None:
        """校验只影响 json/json_llm 的输出配置。"""
        if not isinstance(self.json_options, dict):
            raise ValueError("output.json_options 必须是对象")
        if not isinstance(self.include_generation_timestamps, bool):
            raise ValueError(
                "output.json_options.include_generation_timestamps 必须是布尔值"
            )
    
    def _get_filename(self, metadata: TableMetadata, extension: str) -> str:
        """生成标准文件名：database.schema.table.{extension}
        
        Args:
            metadata: 表元数据
            extension: 文件扩展名（如 'sql', 'json', 'md'）
            
        Returns:
            格式化的文件名
        """
        return f"{self.database_name}.{metadata.schema_name}.{metadata.table_name}.{extension}"
    
    def format_and_save(
        self,
        metadata: TableMetadata,
        sample_data: Optional[pd.DataFrame] = None,
        formats_override: Optional[List[str]] = None
    ) -> dict:
        """格式化并保存元数据
        
        Args:
            metadata: 表元数据
            sample_data: 样本数据（可选，用于 Markdown）
            
        Returns:
            保存的文件路径字典 {'ddl': path, 'markdown': path, 'json': path}
        """
        output_files = {}
        active_formats = self.formats if formats_override is None else formats_override
        
        if not active_formats:
            logger.info("未指定输出格式，跳过文件保存")
            return output_files
        
        # 生成 DDL
        if "ddl" in active_formats:
            ddl_path = self._save_ddl(metadata, sample_data)
            if ddl_path:
                output_files["ddl"] = str(ddl_path)
        
        # 生成 Markdown
        if "markdown" in active_formats:
            md_path = self._save_markdown(metadata, sample_data)
            if md_path:
                output_files["markdown"] = str(md_path)
        
        # 生成 JSON
        if "json" in active_formats:
            json_path = self._save_json(metadata, sample_data)
            if json_path:
                output_files["json"] = str(json_path)
        
        return output_files
    
    def generate_ddl(
        self,
        metadata: TableMetadata,
        sample_data: Optional[pd.DataFrame] = None
    ) -> str:
        """生成普通表、View 或 Materialized View 的 DDL 脚本。"""
        object_type = metadata.table_type or "table"
        if object_type not in {"table", "view", "materialized_view"}:
            raise ValueError(f"不支持的数据库对象类型: {object_type}")
        
        ddl_lines = []
        
        # 文件头注释
        ddl_lines.append(f"-- ====================================")
        ddl_lines.append(f"-- Database: {self.database_name}")
        object_header_label = {
            "table": "Table",
            "view": "View",
            "materialized_view": "Materialized View",
        }[object_type]
        ddl_lines.append(f"-- {object_header_label}: {metadata.full_name}")
        ddl_lines.append(f"-- Object Type: {object_type}")
        if metadata.comment:
            ddl_lines.append(f"-- Comment: {metadata.comment}")
        ddl_lines.append(f"-- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        ddl_lines.append(f"-- ====================================")
        ddl_lines.append("")
        
        if object_type == "table":
            ddl_lines.extend(self._build_create_table_statement(metadata))
        else:
            definition = (metadata.view_definition or "").strip().rstrip(";")
            if not definition:
                raise ValueError(f"{metadata.full_name} 缺少 View 定义")
            if object_type == "view":
                ddl_lines.append(
                    f"CREATE OR REPLACE VIEW {metadata.full_name} AS\n{definition};"
                )
            else:
                ddl_lines.append(
                    f"CREATE MATERIALIZED VIEW IF NOT EXISTS {metadata.full_name} AS\n"
                    f"{definition};"
                )
        ddl_lines.append("")
        
        if object_type in {"view", "materialized_view"}:
            ddl_lines.extend(self._build_view_object_metadata_block(metadata))
            ddl_lines.append("")

        # 字段注释
        if self.ddl_options.get("include_comments", True):
            ddl_lines.append("-- Column Comments")
            for col in metadata.columns:
                if col.comment:
                    ddl_lines.append(
                        f"COMMENT ON COLUMN {metadata.full_name}.{col.column_name} IS "
                        f"'{self._escape_sql_comment(col.comment)}';"
                    )
            ddl_lines.append("")

        # 只排除由物理约束创建的索引；独立唯一索引必须保留。
        if self.ddl_options.get("include_indexes", True):
            standalone_indexes = [
                idx for idx in metadata.indexes
                if not idx.is_primary and not idx.is_constraint_backed
            ]

            if standalone_indexes:
                ddl_lines.append("-- Indexes")
                for idx in standalone_indexes:
                    if idx.definition:
                        ddl_lines.append(idx.definition.rstrip().rstrip(";") + ";")
                    else:
                        unique = "UNIQUE " if idx.is_unique else ""
                        ddl_lines.append(
                            f"CREATE {unique}INDEX {idx.index_name} ON "
                            f"{metadata.full_name}({', '.join(idx.columns)});"
                        )
                ddl_lines.append("")

        # 数据库对象注释
        if metadata.comment:
            comment_object_type = {
                "table": "TABLE",
                "view": "VIEW",
                "materialized_view": "MATERIALIZED VIEW",
            }[object_type]
            ddl_lines.append("-- Object Comment")
            ddl_lines.append(
                f"COMMENT ON {comment_object_type} {metadata.full_name} IS "
                f"'{self._escape_sql_comment(metadata.comment)}';"
            )

        sample_block = self._build_sample_records_block(metadata, sample_data)
        if sample_block:
            ddl_lines.append("")
            ddl_lines.append(sample_block)

        return "\n".join(ddl_lines)

    def _build_create_table_statement(self, metadata: TableMetadata) -> List[str]:
        """生成普通表的 CREATE TABLE 语句。"""
        ddl_lines = [f"CREATE TABLE IF NOT EXISTS {metadata.full_name} ("]
        column_defs = []
        for col in metadata.columns:
            rendered_type = format_data_type(
                col.data_type,
                char_length=col.character_maximum_length,
                numeric_precision=col.numeric_precision,
                numeric_scale=col.numeric_scale,
            )
            col_def = f"    {col.column_name} {rendered_type}"
            if not col.is_nullable:
                col_def += " NOT NULL"
            if col.column_default:
                col_def += f" DEFAULT {col.column_default}"
            column_defs.append(col_def)
        
        for pk in metadata.primary_keys:
            column_defs.append(
                f"    CONSTRAINT {pk.constraint_name} PRIMARY KEY "
                f"({', '.join(pk.columns)})"
            )
        for uc in metadata.unique_constraints:
            column_defs.append(
                f"    CONSTRAINT {uc.constraint_name} UNIQUE "
                f"({', '.join(uc.columns)})"
            )
        for fk in metadata.foreign_keys:
            fk_def = (
                f"    CONSTRAINT {fk.constraint_name} FOREIGN KEY "
                f"({', '.join(fk.source_columns)}) REFERENCES "
                f"{fk.target_schema}.{fk.target_table} "
                f"({', '.join(fk.target_columns)})"
            )
            if fk.on_delete != "NO ACTION":
                fk_def += f" ON DELETE {fk.on_delete}"
            if fk.on_update != "NO ACTION":
                fk_def += f" ON UPDATE {fk.on_update}"
            column_defs.append(fk_def)
        
        ddl_lines.append(",\n".join(column_defs))
        ddl_lines.append(");")
        return ddl_lines
        
    @staticmethod
    def _build_view_object_metadata_block(metadata: TableMetadata) -> List[str]:
        """生成 View/MV 的对象注释和字段元数据块。"""
        object_type = metadata.table_type or "table"
        payload = {
            "object_type": object_type,
            "object_name": metadata.full_name,
            "object_comment": metadata.comment or "",
            "columns": [
                {
                    "column_name": column.column_name,
                    "data_type": format_data_type(
                        column.data_type,
                        char_length=column.character_maximum_length,
                        numeric_precision=column.numeric_precision,
                        numeric_scale=column.numeric_scale,
                    ).lower(),
                    "column_comment": column.comment or "",
                }
                for column in metadata.columns
            ],
        }
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        return ["/* OBJECT_METADATA", *serialized.splitlines(), "*/"]

    @staticmethod
    def _escape_sql_comment(value: str) -> str:
        return value.replace("'", "''")
    
    def _get_sample_value(
        self,
        column_name: str,
        sample_data: Optional[pd.DataFrame]
    ) -> str:
        """从样本数据中获取字段的第一个非空值
        
        Args:
            column_name: 字段名
            sample_data: 样本数据
            
        Returns:
            字段的示例值，如果为空或不存在则返回 "null"
        """
        if sample_data is None or sample_data.empty:
            return "null"

        if column_name not in sample_data.columns:
            return "null"

        non_null_values = sample_data[column_name].dropna()
        if non_null_values.empty:
            return "null"

        sample_values = (
            non_null_values.iloc[: self.markdown_sample_value_count]
            .astype(str)
            .tolist()
        )

        if not sample_values:
            return "null"

        return ", ".join(sample_values)
    
    def generate_markdown(
        self,
        metadata: TableMetadata,
        sample_data: Optional[pd.DataFrame] = None
    ) -> str:
        """生成 Markdown 文档
        
        Args:
            metadata: 表元数据
            sample_data: 样本数据（可选）
            
        Returns:
            Markdown 文档内容
        """
        md_lines = []
        
        # 1. 标题：schema.object_name [object_type]（对象注释）
        object_type = metadata.table_type or "table"
        if object_type not in {"table", "view", "materialized_view"}:
            raise ValueError(f"不支持的数据库对象类型: {object_type}")
        comment_part = f"（{metadata.comment}）" if metadata.comment else ""
        md_lines.append(f"# {metadata.full_name} [{object_type}]{comment_part}")
        
        # 2. 字段列表
        md_lines.append("## 字段列表：")
        
        for col in metadata.columns:
            # 构建类型字符串（含长度/精度）
            data_type = format_data_type(
                col.data_type,
                char_length=col.character_maximum_length,
                numeric_precision=col.numeric_precision,
                numeric_scale=col.numeric_scale,
            ).lower()
            
            # 获取示例值
            sample_value = self._get_sample_value(col.column_name, sample_data)
            
            # 字段注释
            comment = col.comment if col.comment else "无注释"
            
            # 生成字段行
            md_lines.append(f"- {col.column_name} ({data_type}) - {comment} [示例: {sample_value}]")
        
        # 3. 字段补充说明
        supplementary_items = []
        
        # 3.1 主键约束
        if metadata.primary_keys:
            for pk in metadata.primary_keys:
                cols = ', '.join(pk.columns)
                supplementary_items.append(f"- 主键约束 {pk.constraint_name}: {cols}")
        
        # 3.2 外键关系
        if metadata.foreign_keys:
            for fk in metadata.foreign_keys:
                source_cols = ', '.join(fk.source_columns)
                target_cols = ', '.join(fk.target_columns)
                supplementary_items.append(
                    f"- 外键约束 {source_cols} 关联 {fk.target_schema}.{fk.target_table}.{target_cols}"
                )
        
        # 3.3 逻辑主键 - 已禁用，不在 Markdown 中显示
        # if metadata.logical_keys:
        #     for lk in metadata.logical_keys:
        #         cols = ', '.join(lk.columns)
        #         supplementary_items.append(
        #             f"- 逻辑主键候选：{cols} (置信度: {lk.confidence_score:.2f})"
        #         )
        
        # 3.4 唯一约束
        if metadata.unique_constraints:
            for uc in metadata.unique_constraints:
                cols = ', '.join(uc.columns)
                supplementary_items.append(f"- 唯一约束 {uc.constraint_name}: {cols}")
        
        # 3.5 独立索引（排除主键和唯一约束的支撑索引）
        standalone_indexes = [
            idx for idx in metadata.indexes
            if not idx.is_primary and not idx.is_constraint_backed
        ]
        if standalone_indexes:
            for idx in standalone_indexes:
                keys = (
                    idx.key_expressions
                    if idx.key_expressions is not None
                    else idx.columns
                )
                key_text = ", ".join(keys)
                if not key_text:
                    key_text = idx.definition or "无法解析索引键"
                index_label = "唯一索引" if idx.is_unique else "索引"
                suffix = ""
                if idx.included_columns:
                    suffix += f"；INCLUDE: {', '.join(idx.included_columns)}"
                if idx.condition:
                    suffix += f"；WHERE: {idx.condition}"
                supplementary_items.append(
                    f"- {index_label} {idx.index_name} ({idx.index_type}): "
                    f"{key_text}{suffix}"
                )
        
        # 3.6 数据类型精度说明（针对 numeric/decimal 类型）
        numeric_cols = [
            col for col in metadata.columns 
            if 'numeric' in col.data_type.lower() or 'decimal' in col.data_type.lower()
        ]
        if numeric_cols:
            for col in numeric_cols:
                if col.numeric_precision and col.numeric_scale:
                    supplementary_items.append(
                        f"- {col.column_name} 使用{col.data_type}({col.numeric_precision},{col.numeric_scale})"
                        f"存储，精确到小数点后{col.numeric_scale}位"
                    )
        
        # 只有当有补充说明内容时才显示这一节
        if supplementary_items:
            md_lines.append("## 字段补充说明：")
            md_lines.extend(supplementary_items)
        
        return "\n".join(md_lines)
    
    def _save_ddl(
        self,
        metadata: TableMetadata,
        sample_data: Optional[pd.DataFrame] = None
    ) -> Optional[Path]:
        """保存 DDL 脚本"""
        try:
            ddl_content = self.generate_ddl(metadata, sample_data)
            filename = self._get_filename(metadata, "sql")
            file_path = self.ddl_dir / filename
            save_text(ddl_content, file_path)
            logger.info(f"保存 DDL: {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"保存 DDL 失败 ({metadata.full_name}): {e}")
            return None
    
    def _save_markdown(
        self,
        metadata: TableMetadata,
        sample_data: Optional[pd.DataFrame] = None
    ) -> Optional[Path]:
        """保存 Markdown 文档"""
        try:
            md_content = self.generate_markdown(metadata, sample_data)
            filename = self._get_filename(metadata, "md")
            file_path = self.markdown_dir / filename
            save_text(md_content, file_path)
            logger.info(f"保存 Markdown: {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"保存 Markdown 失败 ({metadata.full_name}): {e}")
            return None
    
    def _extract_sample_records_from_ddl(self, metadata: TableMetadata) -> Optional[Dict[str, Any]]:
        """从 DDL 文件中提取样例记录
        
        Args:
            metadata: 表元数据
            
        Returns:
            样例记录字典，如果没有找到则返回 None
        """
        try:
            filename = self._get_filename(metadata, "sql")
            ddl_file = self.ddl_dir / filename
            if not ddl_file.exists():
                return None
            
            content = ddl_file.read_text(encoding="utf-8")
            
            # 新格式使用 SAMPLED_RECORDS，同时兼容历史 SAMPLE_RECORDS。
            pattern = (
                r'/\*\s*(?:SAMPLED_RECORDS|SAMPLE_RECORDS)\s*'
                r'(?P<body>\{.*?\})\s*\*/'
            )
            match = re.search(pattern, content, re.DOTALL)
            
            if not match:
                return None
            
            json_str = match.group("body")
            sample_data = json.loads(json_str)
            
            # 新格式直接保存记录；旧格式使用 {label, data} 包装。
            records = []
            for record in sample_data.get("records", []):
                if not isinstance(record, dict):
                    continue
                record_data = record.get("data") if "data" in record else record
                if not isinstance(record_data, dict):
                    continue

                # 转换数据类型（将字符串数字转换为数字）
                converted_data = {}
                for key, value in record_data.items():
                    if isinstance(value, str):
                        try:
                            if '.' not in value:
                                converted_data[key] = int(value)
                            else:
                                converted_data[key] = float(value)
                        except (ValueError, TypeError):
                            converted_data[key] = value
                    else:
                        converted_data[key] = value
                records.append(converted_data)
            
            if not records:
                return None

            max_records = self.sample_record_options["count"]
            selected_records = records[:max_records]
            return {
                "sample_method": sample_data.get("sample_method", "limit"),
                "sample_size": len(selected_records),
                "total_rows": metadata.row_count,
                "records": selected_records,
            }
            
        except Exception as e:
            logger.warning(f"从 DDL 提取样例数据失败 ({metadata.full_name}): {e}")
            return None
    
    def build_json_document(
        self,
        metadata: TableMetadata,
        sample_data: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """在内存中构造并校验一份 JSON 3.0 文档。"""
        self.validate_json_options()
        profiling_sample_count = None if sample_data is None else len(sample_data)
        json_data = metadata.to_dict(
            include_generation_timestamp=self.include_generation_timestamps,
            profiling_sample_method="limit",
            profiling_sample_count=profiling_sample_count,
        )

        sample_records = self._extract_sample_records_from_ddl(metadata)
        if not sample_records and sample_data is not None and not sample_data.empty:
            samples = dataframe_to_sample_dict(
                sample_data,
                max_rows=self.sample_record_options["count"],
            )
            if samples:
                sample_records = {
                    "sample_method": "limit",
                    "records": samples,
                }

        if not sample_records:
            sample_records = {"sample_method": "none", "records": []}

        json_data["sample_records"] = {
            "sample_method": sample_records["sample_method"],
            "records": sample_records["records"],
        }
        MetadataDocument.from_dict(json_data)
        return json_data

    def json_output_path(self, metadata: TableMetadata) -> Path:
        """返回对象对应的 JSON 输出路径。"""
        return self.json_dir / self._get_filename(metadata, "json")

    def save_json_document(
        self,
        document: Dict[str, Any],
        file_path: str | Path,
    ) -> Path:
        """校验并原子保存已完成规则/LLM 合并的 JSON 文档。"""
        MetadataDocument.from_dict(document)
        saved_path = atomic_write_json(document, file_path)
        logger.info("保存 JSON: %s", saved_path)
        return saved_path

    def _save_json(
        self,
        metadata: TableMetadata,
        sample_data: Optional[pd.DataFrame] = None,
    ) -> Optional[Path]:
        """兼容 format_and_save 的 JSON 保存入口。"""
        try:
            document = self.build_json_document(metadata, sample_data)
            return self.save_json_document(document, self.json_output_path(metadata))
        except Exception as e:
            logger.error(f"保存 JSON 失败 ({metadata.full_name}): {e}")
            return None

    def _build_sample_records_block(
        self,
        metadata: TableMetadata,
        sample_data: Optional[pd.DataFrame]
    ) -> str:
        """构建样例记录注释块"""
        if not self.sample_record_options.get("enabled", True):
            return ""
        
        max_records = self.sample_record_options["count"]
        if max_records == 0:
            return ""
        
        samples = []
        if sample_data is not None and not sample_data.empty:
            samples = dataframe_to_sample_dict(sample_data, max_rows=max_records)

        records = samples[:max_records]
        
        if not records:
            return ""
        
        payload = {
            "object_type": metadata.table_type or "table",
            "object_name": metadata.full_name,
            "records": records,
        }
        json_block = json.dumps(payload, ensure_ascii=False, indent=2)
        return "\n".join(["/* SAMPLED_RECORDS", json_block, "*/"])
