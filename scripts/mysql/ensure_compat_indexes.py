from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
ENV_FILE = ROOT / "apps" / "api" / ".env.mysql"

if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

from app.core.mysql_schema import ensure_mysql_compat_indexes  # noqa: E402


def main() -> None:
    applied, skipped = asyncio.run(ensure_mysql_compat_indexes())
    print(f"mysql_compat_indexes=ok applied={applied} skipped={skipped}")


if __name__ == "__main__":
    main()
