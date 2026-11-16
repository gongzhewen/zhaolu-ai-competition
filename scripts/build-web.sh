#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB="$ROOT/apps/web"

cd "$WEB"
if [[ ! -f package-lock.json ]]; then
  npm install --registry=https://registry.npmmirror.com
else
  npm ci --registry=https://registry.npmmirror.com
fi
npm run build
echo "前端构建完成：$WEB/dist"
