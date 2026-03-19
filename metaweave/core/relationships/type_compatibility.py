"""类型兼容性判断模块

提供跨模块共享的 PostgreSQL 类型约束、规范化及兼容性评分规则。
"""

def normalize_pg_type(data_type: str) -> str:
    """标准化数据类型"""
    if not data_type:
        return ""

    # 转小写并去除空格
    normalized = data_type.lower().strip()

    # 移除precision/scale（如 numeric(10,2) -> numeric）
    if "(" in normalized:
        normalized = normalized.split("(")[0].strip()

    return normalized


def get_type_compatibility_score(type1: str, type2: str) -> float:
    """计算PostgreSQL两个类型的JOIN兼容性分数
    
    评分标准：
    - 1.0: 类型完全相同
    - 0.9: 同类型族，完全互换，零损失（如 INTEGER ↔ BIGINT, INTEGER ↔ NUMERIC）
    - 0.85: 同大类，高度兼容，实际使用无影响（如 VARCHAR ↔ TEXT）
    - 0.8: 同大族，兼容但有细微差异（如 CHAR参与, NUMERIC不同精度, TIMESTAMP时区转换）
    - 0.6: 可以JOIN但有精度问题（如 INTEGER ↔ FLOAT）
    - 0.5: 可以JOIN但精度损失明显（如 DATE ↔ TIMESTAMP, NUMERIC ↔ FLOAT）
    - 0.0: JOIN会报错，完全不兼容
    
    Args:
        type1: PostgreSQL类型1
        type2: PostgreSQL类型2
        
    Returns:
        float: 兼容性分数 [0.0, 1.0]
    """
    # 标准化类型
    t1 = normalize_pg_type(type1)
    t2 = normalize_pg_type(type2)
    
    # 1.0 - 完全相同
    if t1 == t2:
        return 1.0
    
    # ===== 整数类型族 =====
    int_small = {"smallint", "int2", "smallserial"}
    int_standard = {"integer", "int", "int4", "serial"}
    int_big = {"bigint", "int8", "bigserial"}
    int_all = int_small | int_standard | int_big
    
    # 0.9 - 整数族内部，完全互换
    if t1 in int_all and t2 in int_all:
        return 0.9
    
    # ===== 字符串类型族 =====
    # VARCHAR/TEXT 组（无padding问题）
    str_varchar = {"varchar", "character varying", "text"}
    # CHAR 组（有padding陷阱）
    str_char = {"char", "character", "bpchar"}
    str_all = str_varchar | str_char
    
    # 0.85 - VARCHAR/TEXT之间（安全）
    if t1 in str_varchar and t2 in str_varchar:
        return 0.85
    
    # 0.8 - CHAR参与时（有padding陷阱）
    if t1 in str_all and t2 in str_all:
        return 0.8
    
    # ===== 精确数值类型族 =====
    numeric_types = {"numeric", "decimal"}
    
    # 0.8 - NUMERIC/DECIMAL之间（精度可能不同）
    if t1 in numeric_types and t2 in numeric_types:
        return 0.8
    
    # ===== 浮点数值类型族 =====
    float_types = {"real", "float4", "double precision", "float8", "float"}
    
    # 0.8 - 浮点类型之间
    if t1 in float_types and t2 in float_types:
        return 0.8
    
    # ===== 整数与数值类型交叉 =====
    # 0.9 - 整数与NUMERIC（整数可以无损转为NUMERIC）
    if (t1 in int_all and t2 in numeric_types) or (t1 in numeric_types and t2 in int_all):
        return 0.9
    
    # 0.6 - 整数与浮点（有精度损失）
    if (t1 in int_all and t2 in float_types) or (t1 in float_types and t2 in int_all):
        return 0.6
    
    # 0.5 - NUMERIC与浮点（精确数值vs浮点，精度损失明显）
    if (t1 in numeric_types and t2 in float_types) or (t1 in float_types and t2 in numeric_types):
        return 0.5
    
    # ===== 日期时间类型族 =====
    date_types = {"date"}
    
    timestamp_without_tz = {"timestamp", "timestamp without time zone"}
    
    timestamp_with_tz = {"timestamp with time zone", "timestamptz"}
    
    timestamp_all = timestamp_without_tz | timestamp_with_tz
    
    time_types = {"time", "time without time zone", "time with time zone", "timetz"}
    
    # 1.0 - DATE 与 DATE
    if t1 in date_types and t2 in date_types:
        return 1.0
    
    # 0.9 - TIMESTAMP系列内部（同义词）
    if t1 in timestamp_without_tz and t2 in timestamp_without_tz:
        return 0.9
    
    if t1 in timestamp_with_tz and t2 in timestamp_with_tz:
        return 0.9
    
    # 0.8 - TIMESTAMP WITH TZ vs WITHOUT TZ（有时区转换）
    if (t1 in timestamp_without_tz and t2 in timestamp_with_tz) or \
       (t1 in timestamp_with_tz and t2 in timestamp_without_tz):
        return 0.8
    
    # 0.5 - DATE vs TIMESTAMP（精度损失明显：DATE只能匹配午夜00:00:00）
    if (t1 in date_types and t2 in timestamp_all) or \
       (t1 in timestamp_all and t2 in date_types):
        return 0.5
    
    # 0.85 - TIME系列内部
    if t1 in time_types and t2 in time_types:
        return 0.85
    
    # 0.0 - TIME vs DATE/TIMESTAMP（不能JOIN）
    if (t1 in time_types and (t2 in date_types or t2 in timestamp_all)) or \
       ((t1 in date_types or t1 in timestamp_all) and t2 in time_types):
        return 0.0
    
    # ===== 布尔类型 =====
    bool_types = {"boolean", "bool"}
    
    if t1 in bool_types and t2 in bool_types:
        return 0.9  # 同义词
    
    # 0.6 - BOOLEAN vs INTEGER（可JOIN但语义奇怪）
    if (t1 in bool_types and t2 in int_all) or (t1 in int_all and t2 in bool_types):
        return 0.6
    
    # ===== UUID类型 =====
    uuid_types = {"uuid"}
    
    if t1 in uuid_types and t2 in uuid_types:
        return 1.0
    
    # ===== 跨大类：全部不兼容 =====
    # 数值类型 vs 字符串类型 → 0.0
    all_numeric = int_all | numeric_types | float_types
    if (t1 in all_numeric and t2 in str_all) or (t1 in str_all and t2 in all_numeric):
        return 0.0
    
    # 时间类型 vs 字符串类型 → 0.0
    all_time = date_types | timestamp_all | time_types
    if (t1 in all_time and t2 in str_all) or (t1 in str_all and t2 in all_time):
        return 0.0
    
    # UUID vs 其他类型 → 0.0
    if (t1 in uuid_types and t2 not in uuid_types) or (t1 not in uuid_types and t2 in uuid_types):
        return 0.0
    
    # 布尔 vs 其他非数值类型 → 0.0
    if (t1 in bool_types and t2 not in (bool_types | int_all)) or \
       (t1 not in (bool_types | int_all) and t2 in bool_types):
        return 0.0
    
    # ===== 其他未知类型组合 =====
    return 0.0


def meets_type_compatibility_threshold(type1: str, type2: str, threshold: float) -> bool:
    """检查类型兼容性是否达到阈值"""
    return get_type_compatibility_score(type1, type2) >= threshold
