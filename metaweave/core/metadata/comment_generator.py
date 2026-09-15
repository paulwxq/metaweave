"""注释生成器

使用 LLM 生成表和字段的注释。
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import pandas as pd

from metaweave.services.llm_service import LLMService
from metaweave.core.metadata.models import TableMetadata
from metaweave.core.metadata.comment_utils import normalize_comment
from metaweave.utils.data_utils import dataframe_to_sample_dict

logger = logging.getLogger("metaweave.comment_generator")


@dataclass(frozen=True)
class CommentGenerationFailure:
    """一个对象或字段注释生成失败。"""

    target: str
    reason: str


@dataclass
class CommentGenerationResult:
    """单个数据库对象的 DDL 注释生成结果。"""

    request_count: int = 0
    object_success_count: int = 0
    object_failure_count: int = 0
    column_success_count: int = 0
    column_failure_count: int = 0
    failures: List[CommentGenerationFailure] = field(default_factory=list)

    @property
    def generated_count(self) -> int:
        return self.object_success_count + self.column_success_count

    @property
    def has_failures(self) -> bool:
        return bool(self.failures)


class CommentGenerator:
    """注释生成器
    
    使用 LLM 生成表和字段的注释。
    """
    
    def __init__(
        self,
        llm_service: LLMService
    ):
        """初始化注释生成器
        
        Args:
            llm_service: LLM 服务实例
        """
        self.llm_service = llm_service

        logger.info("注释生成器已初始化")
    
    def generate_table_comment(
        self,
        metadata: TableMetadata,
        sample_data: Optional[pd.DataFrame] = None,
        force_regenerate: bool = False
    ) -> str:
        """生成表注释
        
        Args:
            metadata: 表元数据
            sample_data: 样本数据（可选）
            force_regenerate: 是否强制重新生成（忽略缓存）
            
        Returns:
            生成的表注释
        """
        # 准备字段信息
        columns = [
            {"name": col.column_name, "type": col.data_type}
            for col in metadata.columns
        ]
        
        # 准备样本数据
        sample_dict = None
        if sample_data is not None and not sample_data.empty:
            # 统一使用最多5行样本数据，便于 LLM 理解表结构
            sample_dict = dataframe_to_sample_dict(sample_data, max_rows=5)
        
        # 调用 LLM 生成注释
        try:
            logger.debug("CommentGenerator 当前 LLM 模型: %s", self.llm_service.model)
            comment = self.llm_service.generate_table_comment(
                table_name=metadata.table_name,
                columns=columns,
                sample_data=sample_dict
            )
            
            comment = normalize_comment(comment)
            if comment:
                logger.info(f"生成表注释: {metadata.full_name}")
                return comment
            else:
                logger.warning(f"LLM 返回空注释: {metadata.full_name}")
                return ""
        
        except Exception as e:
            logger.error(f"生成表注释失败 ({metadata.full_name}): {e}")
            return ""
    
    def generate_column_comments(
        self,
        metadata: TableMetadata,
        sample_data: Optional[pd.DataFrame] = None,
        force_regenerate: bool = False
    ) -> Dict[str, str]:
        """批量生成字段注释
        
        Args:
            metadata: 表元数据
            sample_data: 样本数据（可选）
            force_regenerate: 是否强制重新生成（忽略缓存）
            
        Returns:
            字段注释字典 {column_name: comment}
        """
        # 筛选需要生成注释的字段
        columns_need_comment = [
            col for col in metadata.columns
            if not normalize_comment(col.comment) or force_regenerate
        ]
        
        if not columns_need_comment:
            logger.info(f"所有字段都有注释: {metadata.full_name}")
            return {}
        
        # 准备字段信息（包含样本值）
        columns_info = []
        for col in columns_need_comment:
            col_info = {
                "name": col.column_name,
                "type": col.data_type,
            }
            
            # 添加样本值
            if sample_data is not None and col.column_name in sample_data.columns:
                sample_values = sample_data[col.column_name].dropna().head(5).tolist()
                col_info["sample_values"] = sample_values
            
            columns_info.append(col_info)
        
        # 准备样本数据
        sample_dict = None
        if sample_data is not None and not sample_data.empty:
            # 与表注释一致，最多提供5行样本数据
            sample_dict = dataframe_to_sample_dict(sample_data, max_rows=5)
        
        # 调用 LLM 生成注释
        try:
            logger.debug("CommentGenerator 当前 LLM 模型: %s", self.llm_service.model)
            comments = self.llm_service.generate_column_comments(
                table_name=metadata.table_name,
                columns=columns_info,
                sample_data=sample_dict
            )
            
            if comments:
                logger.info(f"生成字段注释: {metadata.full_name}, {len(comments)} 个字段")
                return comments
            else:
                logger.warning(f"LLM 返回空注释: {metadata.full_name}")
                return {}
        
        except Exception as e:
            logger.error(f"生成字段注释失败 ({metadata.full_name}): {e}")
            return {}
    
    def enrich_metadata_with_comments(
        self,
        metadata: TableMetadata,
        sample_data: Optional[pd.DataFrame] = None,
        overwrite: bool = False,
    ) -> CommentGenerationResult:
        """使用 LLM 增强元数据的注释
        
        Args:
            metadata: 表元数据（会被修改）
            sample_data: 样本数据（可选）
            overwrite: ``False`` 仅补缺失注释；``True`` 全量刷新注释。

        Returns:
            包含逐项成功、失败和请求次数的结构化结果。当前每个对象注释任务
            计一次逻辑请求，所有待处理字段合并为一次字段注释请求；如将来增加
            DDL 字段分批调用，必须同步按实际调用次数更新 ``request_count``。
        """
        result = CommentGenerationResult()

        metadata.comment = normalize_comment(metadata.comment)
        if not metadata.comment:
            metadata.comment_source = ""
        for column in metadata.columns:
            column.comment = normalize_comment(column.comment)
            if not column.comment:
                column.comment_source = ""

        # 对象注释与字段注释分别判定和统计，允许部分成功。
        if overwrite or not metadata.comment:
            result.request_count += 1
            comment = normalize_comment(
                self.generate_table_comment(
                    metadata,
                    sample_data,
                    force_regenerate=overwrite,
                )
            )
            if comment:
                metadata.comment = comment
                metadata.comment_source = "llm_generated"
                result.object_success_count += 1
            else:
                metadata.comment = ""
                metadata.comment_source = ""
                result.object_failure_count += 1
                result.failures.append(
                    CommentGenerationFailure(
                        target=metadata.full_name,
                        reason="LLM 未返回有效对象注释",
                    )
                )

        requested_columns = [
            column
            for column in metadata.columns
            if overwrite or not column.comment
        ]
        if requested_columns:
            result.request_count += 1
            column_comments = self.generate_column_comments(
                metadata,
                sample_data,
                force_regenerate=overwrite,
            )
        else:
            column_comments = {}

        for column in requested_columns:
            comment = normalize_comment(column_comments.get(column.column_name))
            if comment:
                column.comment = comment
                column.comment_source = "llm_generated"
                result.column_success_count += 1
            else:
                column.comment = ""
                column.comment_source = ""
                result.column_failure_count += 1
                result.failures.append(
                    CommentGenerationFailure(
                        target=f"{metadata.full_name}.{column.column_name}",
                        reason="LLM 未返回有效字段注释",
                    )
                )

        for failure in result.failures:
            logger.warning("注释生成失败 %s: %s", failure.target, failure.reason)
        logger.info(
            "生成注释完成: %s，成功 %d，失败 %d",
            metadata.full_name,
            result.generated_count,
            result.object_failure_count + result.column_failure_count,
        )
        return result
