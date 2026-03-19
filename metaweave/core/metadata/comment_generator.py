"""注释生成器

使用 LLM 生成表和字段的注释。
"""

import logging
from typing import List, Dict, Optional, Any
import pandas as pd

from metaweave.services.llm_service import LLMService
from metaweave.core.metadata.models import TableMetadata
from metaweave.utils.data_utils import dataframe_to_sample_dict

logger = logging.getLogger("metaweave.comment_generator")


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
            if not col.comment or force_regenerate
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
    ) -> int:
        """使用 LLM 增强元数据的注释
        
        Args:
            metadata: 表元数据（会被修改）
            sample_data: 样本数据（可选）
            
        Returns:
            生成的注释数量
        """
        generated_count = 0
        
        # 生成表注释（仅缺失时生成）
        if not metadata.comment:
            comment = self.generate_table_comment(metadata, sample_data)
            if comment:
                metadata.comment = comment
                metadata.comment_source = "llm_generated"
                generated_count += 1
        
        # 生成字段注释（仅缺失字段会被 generate_column_comments 筛选）
        column_comments = self.generate_column_comments(metadata, sample_data)

        # 更新字段注释
        for column in metadata.columns:
            if column.column_name in column_comments:
                column.comment = column_comments[column.column_name]
                column.comment_source = "llm_generated"
                generated_count += 1
        
        logger.info(f"生成注释完成: {metadata.full_name}, {generated_count} 个注释")
        return generated_count
