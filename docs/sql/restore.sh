#!/usr/bin/env bash
# 将 docs/sql 中的 orders 结构与数据还原到目标 PostgreSQL 数据库。
#
# 用法：
#   PGHOST=127.0.0.1 PGPORT=5432 PGUSER=postgres PGPASSWORD=postgres \
#     ./restore.sh [target_db]
#
# 默认目标库名：orders
# 若目标库不存在则自动创建。脚本会先加载 schema，再加载 data（含物化视图刷新）。

set -euo pipefail

TARGET_DB="${1:-orders}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ ! "${TARGET_DB}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "非法数据库名: ${TARGET_DB}" >&2
  exit 1
fi

if [[ ! -f "${SCRIPT_DIR}/orders_schema.sql" || ! -f "${SCRIPT_DIR}/orders_data.sql" ]]; then
  echo "缺少 orders_schema.sql 或 orders_data.sql" >&2
  exit 1
fi

export PGHOST="${PGHOST:-localhost}"
export PGPORT="${PGPORT:-5432}"
export PGUSER="${PGUSER:-postgres}"

echo "还原目标：${PGUSER}@${PGHOST}:${PGPORT}/${TARGET_DB}"

EXISTS="$(psql -d postgres -Atqc "SELECT 1 FROM pg_database WHERE datname = '${TARGET_DB}'")"
if [[ "${EXISTS}" != "1" ]]; then
  echo "创建数据库 ${TARGET_DB}"
  createdb "${TARGET_DB}"
fi

psql -d "${TARGET_DB}" -v ON_ERROR_STOP=1 -f "${SCRIPT_DIR}/orders_schema.sql"
psql -d "${TARGET_DB}" -v ON_ERROR_STOP=1 -f "${SCRIPT_DIR}/orders_data.sql"

echo "还原完成。"
psql -d "${TARGET_DB}" -c "
SELECT 'categories' AS object_name, count(*) FROM public.categories
UNION ALL SELECT 'cinema_halls', count(*) FROM public.cinema_halls
UNION ALL SELECT 'orders', count(*) FROM public.orders
UNION ALL SELECT 'products', count(*) FROM public.products
UNION ALL SELECT 'screenings', count(*) FROM public.screenings
UNION ALL SELECT 'users', count(*) FROM public.users
UNION ALL SELECT 'mv_category_sales', count(*) FROM public.mv_category_sales
ORDER BY 1;
"
