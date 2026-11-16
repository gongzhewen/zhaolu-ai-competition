#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/packages/agent_core:$ROOT/packages/data_contracts:$ROOT/apps/api${PYTHONPATH:+:$PYTHONPATH}"


PYTHON="${PYTHON_EXE:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  echo "Python 解释器不存在：$PYTHON。请设置 PYTHON_EXE。" >&2
  exit 1
fi
if [[ "${1:-}" == "--live" ]]; then
  if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "运行 MySQL 全量回归前必须设置 DATABASE_URL。" >&2
    exit 1
  fi
  export LIVE_MYSQL_TESTS=1
else
  export LIVE_MYSQL_TESTS=0
fi
if [[ "${2:-}" == "--vector" || "${1:-}" == "--vector" ]]; then
  export LIVE_VECTOR_RAG_TESTS=1
else
  export LIVE_VECTOR_RAG_TESTS=0
  export RAG_VECTOR_ENABLED="${RAG_VECTOR_ENABLED:-false}"
fi

"$PYTHON" -m pytest -q
if [[ "${LIVE_MYSQL_TESTS}" == "1" ]]; then
  "$PYTHON" scripts/mysql/ensure_compat_indexes.py
  "$PYTHON" scripts/mysql/verify_data_consistency.py
  "$PYTHON" scripts/mysql/verify_rollup_self_heal.py
  "$PYTHON" scripts/mysql/verify_regression.py
fi

echo "full_regression=ok live=${LIVE_MYSQL_TESTS} vector=${LIVE_VECTOR_RAG_TESTS}"
