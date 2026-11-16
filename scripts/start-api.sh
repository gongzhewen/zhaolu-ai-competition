#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT/apps/api/.env.mysql}"
HOST_ADDRESS="${HOST_ADDRESS:-0.0.0.0}"
PORT="${PORT:-8000}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "未找到环境文件：$ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "未找到 .venv，请先安装 pyproject.toml 依赖。" >&2
  exit 1
fi

exec "$PYTHON" -m uvicorn app.main:app --host "$HOST_ADDRESS" --port "$PORT"
