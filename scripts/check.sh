#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="$ROOT/.venv/bin/python"
ALEMBIC="$ROOT/.venv/bin/alembic"

if [[ ! -x "$PYTHON" ]]; then
  echo "未找到 .venv，请先创建 Python 虚拟环境并安装依赖。" >&2
  exit 1
fi

"$PYTHON" -m pytest -q

SCHEMA_FILE="${TMPDIR:-/tmp}/zhaolu-ai-v2-schema.sql"
"$ALEMBIC" -c apps/api/alembic.ini upgrade head --sql > "$SCHEMA_FILE"
echo "数据库离线迁移 SQL 已生成：$SCHEMA_FILE"
echo "SQL 行数：$(wc -l < "$SCHEMA_FILE")"
