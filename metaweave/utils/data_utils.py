"""数据处理工具函数"""

import json
import logging
from typing import List, Any, Optional
import pandas as pd

logger = logging.getLogger("metaweave.data_utils")


def calculate_uniqueness(data: pd.DataFrame, columns: List[str]) -> float:
    """计算指定列的唯一度
    
    唯一度 = 不重复值的数量 / 总行数
    
    Args:
        data: 数据 DataFrame
        columns: 要计算的列名列表
        
    Returns:
        唯一度 (0.0 ~ 1.0)
    """
    if data.empty or not columns:
        return 0.0
    
    try:
        # 检查列是否存在
        for col in columns:
            if col not in data.columns:
                logger.warning(f"列不存在: {col}")
                return 0.0
        
        # 计算指定列组合的唯一值数量
        if len(columns) == 1:
            unique_count = data[columns[0]].nunique()
        else:
            unique_count = data[columns].drop_duplicates().shape[0]
        
        total_count = len(data)
        
        if total_count == 0:
            return 0.0
        
        uniqueness = unique_count / total_count
        return round(uniqueness, 4)
    
    except Exception as e:
        logger.error(f"计算唯一度失败: {e}")
        return 0.0


def calculate_null_rate(data: pd.DataFrame, columns: List[str]) -> float:
    """计算指定列的空值率
    
    空值率 = 包含空值的行数 / 总行数
    
    Args:
        data: 数据 DataFrame
        columns: 要计算的列名列表
        
    Returns:
        空值率 (0.0 ~ 1.0)
    """
    if data.empty or not columns:
        return 0.0
    
    try:
        # 检查列是否存在
        for col in columns:
            if col not in data.columns:
                logger.warning(f"列不存在: {col}")
                return 0.0
        
        # 计算包含空值的行数
        null_count = data[columns].isnull().any(axis=1).sum()
        total_count = len(data)
        
        if total_count == 0:
            return 0.0
        
        null_rate = null_count / total_count
        return round(null_rate, 4)
    
    except Exception as e:
        logger.error(f"计算空值率失败: {e}")
        return 0.0


def format_data_type(
    data_type: str,
    char_length: Optional[int] = None,
    numeric_precision: Optional[int] = None,
    numeric_scale: Optional[int] = None
) -> str:
    """格式化数据类型显示
    
    Args:
        data_type: 数据类型
        char_length: 字符最大长度
        numeric_precision: 数值精度
        numeric_scale: 数值小数位数
        
    Returns:
        格式化后的数据类型字符串
    """
    formatted_type = data_type.upper()
    
    # 字符类型
    if data_type in ["character varying", "varchar", "character", "char"] and char_length:
        formatted_type = f"{formatted_type}({char_length})"
    
    # 数值类型
    elif data_type in ["numeric", "decimal"] and numeric_precision:
        if numeric_scale:
            formatted_type = f"{formatted_type}({numeric_precision},{numeric_scale})"
        else:
            formatted_type = f"{formatted_type}({numeric_precision})"
    
    return formatted_type


def truncate_sample(data: pd.DataFrame, max_rows: int = 5) -> pd.DataFrame:
    """截断样本数据到指定行数
    
    Args:
        data: 数据 DataFrame
        max_rows: 最大行数
        
    Returns:
        截断后的 DataFrame
    """
    if len(data) <= max_rows:
        return data
    return data.head(max_rows)


def _is_complex_value(value: Any) -> bool:
    """判断单个值是否为复杂类型（ARRAY/JSON/JSONB/BYTEA 在 psycopg3 下的 Python 映射）"""
    return isinstance(value, (list, tuple, set, dict, bytes))


def _normalize_for_hash(value: Any) -> Any:
    """将复杂值转换为可哈希的稳定字符串表示，用于 nunique / value_counts。

    标量值原样返回；bytes 不应进入此路径（BYTEA 跳过哈希统计）。
    list/tuple 保留元素顺序（PostgreSQL ARRAY 有序），同时通过 sort_keys=True
    递归归一化内嵌 dict 的键顺序（PostgreSQL JSONB 对象键序无关）。
    set 排序后归一化。
    """
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    if isinstance(value, set):
        try:
            return json.dumps(sorted(value), ensure_ascii=False, default=str)
        except TypeError:
            return str(value)
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), ensure_ascii=False, sort_keys=True, default=str)
    return value


def _is_null_value(value: Any) -> bool:
    """安全的空值判断，兼容复杂类型（list/dict/bytes 不走 pd.isna）"""
    if value is None:
        return True
    if _is_complex_value(value):
        return False
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def safe_str(value: Any, max_length: int = 100) -> str:
    """安全转换值为字符串
    
    处理 None、特殊字符、过长字符串等情况。
    
    Args:
        value: 要转换的值
        max_length: 最大长度
        
    Returns:
        字符串表示
    """
    if value is None:
        return ""
    
    try:
        str_value = str(value)
        if len(str_value) > max_length:
            return str_value[:max_length] + "..."
        return str_value
    except Exception:
        return "<unconvertible>"


def dataframe_to_sample_dict(
    df: pd.DataFrame, 
    max_rows: int = 5
) -> List[dict]:
    """将 DataFrame 转换为样本字典列表
    
    Args:
        df: DataFrame
        max_rows: 最大行数
        
    Returns:
        样本字典列表
    """
    if df.empty:
        return []
    
    sample_df = truncate_sample(df, max_rows)
    
    result = []
    for _, row in sample_df.iterrows():
        row_dict = {}
        for col in sample_df.columns:
            try:
                value = row[col]
                if _is_null_value(value):
                    row_dict[col] = None
                elif isinstance(value, bytes):
                    row_dict[col] = f"<binary:{len(value)} bytes>"
                elif isinstance(value, (list, dict)):
                    row_dict[col] = json.dumps(value, ensure_ascii=False, default=str)
                else:
                    row_dict[col] = safe_str(value, max_length=200)
            except Exception as e:
                logger.warning(f"字段序列化失败 ({col}): {e}")
                row_dict[col] = None
        result.append(row_dict)
    return result


def get_column_statistics(
    df: pd.DataFrame, 
    column: str,
    value_distribution_threshold: int = 10
) -> dict:
    """获取列的统计信息
    
    Args:
        df: DataFrame
        column: 列名
        value_distribution_threshold: 唯一值数量阈值，小于等于此值时统计值分布
        
    Returns:
        统计信息字典
    """
    if df.empty or column not in df.columns:
        return {}
    
    try:
        col_data = df[column]

        # --- 全列扫描：检测是否包含复杂类型 --------------------------------
        non_null_values = col_data.dropna()
        is_bytes_col = any(isinstance(v, bytes) for v in non_null_values)
        is_complex_col = (not is_bytes_col) and any(
            _is_complex_value(v) for v in non_null_values
        )

        # --- 基础统计（对所有类型安全） ------------------------------------
        stats = {
            "sample_count": int(len(col_data)),
            "null_count": int(col_data.isnull().sum()),
            "null_rate": float(calculate_null_rate(df, [column])),
        }

        # --- unique_count / uniqueness ------------------------------------
        hashable_series = None
        if is_bytes_col:
            pass  # BYTEA: 跳过，不写入 unique_count / uniqueness
        elif is_complex_col:
            hashable_series = non_null_values.apply(_normalize_for_hash)
            unique_count = int(hashable_series.nunique())
            uniqueness = round(unique_count / len(col_data), 4) if len(col_data) > 0 else 0.0
            stats["unique_count"] = unique_count
            stats["uniqueness"] = uniqueness
        else:
            stats["unique_count"] = int(col_data.nunique())
            stats["uniqueness"] = float(calculate_uniqueness(df, [column]))

        # --- 数值统计（仅数值列） ------------------------------------------
        if pd.api.types.is_numeric_dtype(col_data):
            stats.update({
                "min": safe_str(col_data.min()),
                "max": safe_str(col_data.max()),
                "mean": safe_str(col_data.mean()),
            })

        # --- 字符串长度统计（排除 ARRAY/JSON/JSONB/BYTEA） ------------------
        is_string_col = (
            pd.api.types.is_string_dtype(col_data) or col_data.dtype == object
        ) and not is_complex_col and not is_bytes_col
        if is_string_col:
            if len(non_null_values) > 0:
                lengths = non_null_values.astype(str).str.len()
                stats.update({
                    "avg_length": round(float(lengths.mean()), 2),
                    "min_length": int(lengths.min()),
                    "max_length": int(lengths.max()),
                    "median_length": round(float(lengths.median()), 2),
                    "length_std": round(float(lengths.std()), 2) if len(lengths) > 1 else 0.0,
                })

        # --- value_distribution -------------------------------------------
        if not is_bytes_col:
            effective_unique_count = stats.get("unique_count", 0)
            if effective_unique_count <= value_distribution_threshold:
                if is_complex_col and hashable_series is not None:
                    vc = hashable_series.value_counts().head(10)
                else:
                    vc = col_data.value_counts().head(10)
                stats["value_distribution"] = {
                    safe_str(k): int(v) for k, v in vc.items()
                }

        return stats
    except Exception as e:
        logger.error(f"获取列统计信息失败 ({column}): {e}")
        return {}


def is_potential_key_column(column_name: str) -> bool:
    """判断列名是否可能是主键列
    
    Args:
        column_name: 列名
        
    Returns:
        是否可能是主键
    """
    column_name_lower = column_name.lower()
    key_patterns = ["id", "code", "key", "no", "number", "pk", "_id"]
    
    for pattern in key_patterns:
        if pattern in column_name_lower:
            return True
    
    return False

