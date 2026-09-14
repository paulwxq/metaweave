"""SQL 查询模板

定义从 PostgreSQL 数据库中提取元数据的 SQL 查询模板。
"""

# 获取表信息
GET_TABLE_INFO_SQL = """
SELECT 
    t.schemaname,
    t.tablename,
    obj_description((t.schemaname || '.' || t.tablename)::regclass, 'pg_class') as table_comment,
    COALESCE(pg_stat_get_live_tuples((t.schemaname || '.' || t.tablename)::regclass), 0) as row_count
FROM pg_tables t
WHERE t.schemaname = %s
ORDER BY t.tablename;
"""

# 获取指定表的信息
GET_SINGLE_TABLE_INFO_SQL = """
SELECT 
    t.schemaname,
    t.tablename,
    obj_description((t.schemaname || '.' || t.tablename)::regclass, 'pg_class') as table_comment,
    COALESCE(pg_stat_get_live_tuples((t.schemaname || '.' || t.tablename)::regclass), 0) as row_count
FROM pg_tables t
WHERE t.schemaname = %s AND t.tablename = %s;
"""

# 获取字段信息
GET_COLUMNS_SQL = """
SELECT 
    c.column_name,
    c.ordinal_position,
    c.data_type,
    c.character_maximum_length,
    c.numeric_precision,
    c.numeric_scale,
    c.is_nullable,
    c.column_default,
    pgd.description as column_comment
FROM information_schema.columns c
LEFT JOIN pg_catalog.pg_namespace ns
    ON ns.nspname = c.table_schema
LEFT JOIN pg_catalog.pg_class cls
    ON cls.relnamespace = ns.oid
    AND cls.relname = c.table_name
LEFT JOIN pg_catalog.pg_description pgd 
    ON pgd.objoid = cls.oid
    AND pgd.objsubid = c.ordinal_position
WHERE c.table_schema = %s AND c.table_name = %s
ORDER BY c.ordinal_position;
"""

# 获取主键
GET_PRIMARY_KEYS_SQL = """
SELECT 
    tc.constraint_name,
    array_agg(kcu.column_name ORDER BY kcu.ordinal_position) as columns
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu 
    ON tc.constraint_name = kcu.constraint_name
    AND tc.table_schema = kcu.table_schema
WHERE tc.constraint_type = 'PRIMARY KEY'
    AND tc.table_schema = %s
    AND tc.table_name = %s
GROUP BY tc.constraint_name;
"""

# 获取外键
GET_FOREIGN_KEYS_SQL = """
SELECT
    tc.constraint_name,
    array_agg(DISTINCT kcu.column_name ORDER BY kcu.column_name) as source_columns,
    ccu.table_schema AS target_schema,
    ccu.table_name AS target_table,
    array_agg(DISTINCT ccu.column_name ORDER BY ccu.column_name) as target_columns,
    rc.delete_rule,
    rc.update_rule
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
    AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage ccu
    ON ccu.constraint_name = tc.constraint_name
    AND ccu.table_schema = tc.table_schema
JOIN information_schema.referential_constraints rc
    ON rc.constraint_name = tc.constraint_name
    AND rc.constraint_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
    AND tc.table_schema = %s
    AND tc.table_name = %s
GROUP BY tc.constraint_name, ccu.table_schema, ccu.table_name, 
         rc.delete_rule, rc.update_rule;
"""

# 获取唯一约束
GET_UNIQUE_CONSTRAINTS_SQL = """
SELECT 
    tc.constraint_name,
    array_agg(kcu.column_name ORDER BY kcu.ordinal_position) as columns
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu 
    ON tc.constraint_name = kcu.constraint_name
    AND tc.table_schema = kcu.table_schema
WHERE tc.constraint_type = 'UNIQUE'
    AND tc.table_schema = %s
    AND tc.table_name = %s
GROUP BY tc.constraint_name;
"""

# 获取索引信息（修正版本，处理可能的错误）
GET_INDEXES_SQL = """
SELECT
    i.indexname as index_name,
    am.amname as index_type,
    ix.indisunique as is_unique,
    ix.indisprimary as is_primary,
    (con.oid IS NOT NULL) as is_constraint_backed,
    con.conname as constraint_name,
    pg_get_indexdef(ix.indexrelid) as index_definition,
    pg_get_expr(ix.indpred, ix.indrelid) as condition,
    array_agg(a.attname ORDER BY array_position(ix.indkey::integer[], a.attnum::integer)) as columns
FROM pg_indexes i
JOIN pg_class c ON c.relname = i.tablename AND c.relnamespace = (
    SELECT oid FROM pg_namespace WHERE nspname = i.schemaname
)
JOIN pg_index ix ON ix.indexrelid = (
    SELECT oid FROM pg_class WHERE relname = i.indexname AND relnamespace = (
        SELECT oid FROM pg_namespace WHERE nspname = i.schemaname
    )
)
JOIN pg_class ic ON ic.oid = ix.indexrelid
JOIN pg_am am ON am.oid = ic.relam
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(ix.indkey)
LEFT JOIN pg_constraint con
    ON con.conindid = ix.indexrelid
    AND con.conrelid = c.oid
    AND con.contype IN ('p', 'u', 'x')
WHERE i.schemaname = %s AND i.tablename = %s
GROUP BY i.indexname, am.amname, ix.indisunique, ix.indisprimary, 
         ix.indpred, ix.indrelid, ix.indexrelid, con.oid, con.conname
ORDER BY i.indexname;
"""

# JSON 画像专用的完整索引事实。使用 indnkeyatts 区分索引键与 INCLUDE
# 列，并用 pg_get_indexdef 保留表达式键；不改变 DDL 阶段现有查询行为。
GET_JSON_INDEXES_SQL = """
SELECT
    index_class.relname AS index_name,
    access_method.amname AS index_type,
    index_meta.indisunique AS is_unique,
    index_meta.indisprimary AS is_primary,
    (constraint_meta.oid IS NOT NULL) AS is_constraint_backed,
    constraint_meta.conname AS constraint_name,
    pg_get_indexdef(index_meta.indexrelid) AS index_definition,
    pg_get_expr(index_meta.indpred, index_meta.indrelid) AS condition,
    ARRAY(
        SELECT attribute_meta.attname
        FROM unnest(index_meta.indkey::smallint[]) WITH ORDINALITY AS key_item(attnum, position)
        JOIN pg_catalog.pg_attribute attribute_meta
          ON attribute_meta.attrelid = table_class.oid
         AND attribute_meta.attnum = key_item.attnum
        WHERE key_item.position <= index_meta.indnkeyatts
          AND key_item.attnum <> 0
        ORDER BY key_item.position
    ) AS columns,
    ARRAY(
        SELECT pg_get_indexdef(
            index_meta.indexrelid,
            key_position,
            true
        )
        FROM generate_series(1, index_meta.indnkeyatts) AS key_position
        ORDER BY key_position
    ) AS key_expressions,
    ARRAY(
        SELECT attribute_meta.attname
        FROM unnest(index_meta.indkey::smallint[]) WITH ORDINALITY AS include_item(attnum, position)
        JOIN pg_catalog.pg_attribute attribute_meta
          ON attribute_meta.attrelid = table_class.oid
         AND attribute_meta.attnum = include_item.attnum
        WHERE include_item.position > index_meta.indnkeyatts
          AND include_item.attnum <> 0
        ORDER BY include_item.position
    ) AS included_columns
FROM pg_catalog.pg_class table_class
JOIN pg_catalog.pg_namespace namespace_meta
  ON namespace_meta.oid = table_class.relnamespace
JOIN pg_catalog.pg_index index_meta
  ON index_meta.indrelid = table_class.oid
JOIN pg_catalog.pg_class index_class
  ON index_class.oid = index_meta.indexrelid
JOIN pg_catalog.pg_am access_method
  ON access_method.oid = index_class.relam
LEFT JOIN pg_catalog.pg_constraint constraint_meta
  ON constraint_meta.conindid = index_meta.indexrelid
 AND constraint_meta.conrelid = table_class.oid
 AND constraint_meta.contype IN ('p', 'u', 'x')
WHERE namespace_meta.nspname = %s
  AND table_class.relname = %s
ORDER BY index_class.relname;
"""

# 获取普通表、View 和 Materialized View
GET_DATABASE_OBJECTS_SQL = """
SELECT
    ns.nspname AS schema_name,
    cls.relname AS object_name,
    CASE cls.relkind
        WHEN 'r' THEN 'table'
        WHEN 'p' THEN 'table'
        WHEN 'v' THEN 'view'
        WHEN 'm' THEN 'materialized_view'
    END AS object_type
FROM pg_catalog.pg_class cls
JOIN pg_catalog.pg_namespace ns ON ns.oid = cls.relnamespace
WHERE ns.nspname = %s
  AND cls.relkind::text = ANY(%s)
ORDER BY cls.relname;
"""

# 检查指定类型的数据库对象是否存在
CHECK_DATABASE_OBJECT_EXISTS_SQL = """
SELECT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_class cls
    JOIN pg_catalog.pg_namespace ns ON ns.oid = cls.relnamespace
    WHERE ns.nspname = %s
      AND cls.relname = %s
      AND cls.relkind::text = ANY(%s)
);
"""

# 获取普通表、View 或 Materialized View 的基本信息
GET_DATABASE_OBJECT_INFO_SQL = """
SELECT
    ns.nspname AS schema_name,
    cls.relname AS object_name,
    CASE cls.relkind
        WHEN 'r' THEN 'table'
        WHEN 'p' THEN 'table'
        WHEN 'v' THEN 'view'
        WHEN 'm' THEN 'materialized_view'
    END AS object_type,
    obj_description(cls.oid, 'pg_class') AS object_comment
FROM pg_catalog.pg_class cls
JOIN pg_catalog.pg_namespace ns ON ns.oid = cls.relnamespace
WHERE ns.nspname = %s
  AND cls.relname = %s
  AND cls.relkind::text = ANY(%s);
"""

# 获取 View 或 Materialized View 的查询定义
GET_VIEW_DEFINITION_SQL = """
SELECT pg_get_viewdef(cls.oid, true) AS view_definition
FROM pg_catalog.pg_class cls
JOIN pg_catalog.pg_namespace ns ON ns.oid = cls.relnamespace
WHERE ns.nspname = %s
  AND cls.relname = %s
  AND cls.relkind IN ('v', 'm');
"""

# information_schema.columns 不覆盖 Materialized View，需直接读取系统目录
GET_MATERIALIZED_VIEW_COLUMNS_SQL = """
SELECT
    attr.attname AS column_name,
    attr.attnum AS ordinal_position,
    format_type(attr.atttypid, NULL) AS data_type,
    information_schema._pg_char_max_length(
        attr.atttypid,
        attr.atttypmod
    ) AS character_maximum_length,
    information_schema._pg_numeric_precision(
        attr.atttypid,
        attr.atttypmod
    ) AS numeric_precision,
    information_schema._pg_numeric_scale(
        attr.atttypid,
        attr.atttypmod
    ) AS numeric_scale,
    CASE WHEN attr.attnotnull THEN 'NO' ELSE 'YES' END AS is_nullable,
    pg_get_expr(def.adbin, def.adrelid) AS column_default,
    descr.description AS column_comment
FROM pg_catalog.pg_class cls
JOIN pg_catalog.pg_namespace ns ON ns.oid = cls.relnamespace
JOIN pg_catalog.pg_attribute attr ON attr.attrelid = cls.oid
LEFT JOIN pg_catalog.pg_attrdef def
    ON def.adrelid = cls.oid AND def.adnum = attr.attnum
LEFT JOIN pg_catalog.pg_description descr
    ON descr.objoid = cls.oid AND descr.objsubid = attr.attnum
WHERE ns.nspname = %s
  AND cls.relname = %s
  AND cls.relkind = 'm'
  AND attr.attnum > 0
  AND NOT attr.attisdropped
ORDER BY attr.attnum;
"""

# 获取所有 schema
GET_SCHEMAS_SQL = """
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
ORDER BY schema_name;
"""

# 获取指定 schema 下的所有表
GET_TABLES_SQL = """
SELECT tablename
FROM pg_tables
WHERE schemaname = %s
ORDER BY tablename;
"""

# 数据采样 SQL 模板
SAMPLE_DATA_SQL = """
SELECT * FROM {schema}.{table} LIMIT %s;
"""

# 随机采样 SQL 模板（PostgreSQL TABLESAMPLE）
SAMPLE_DATA_RANDOM_SQL = """
SELECT * FROM {schema}.{table} TABLESAMPLE SYSTEM(%s);
"""

# 检查表是否存在
CHECK_TABLE_EXISTS_SQL = """
SELECT EXISTS (
    SELECT 1
    FROM pg_tables
    WHERE schemaname = %s AND tablename = %s
);
"""
