from __future__ import annotations

import argparse
import asyncio
import json

from app.core.redis_cache import (
    close_redis,
    invalidate_shared_cache,
    shared_get_json,
    shared_set_json,
)
from app.core.runtime_metrics import metrics_snapshot, record_chat_metric


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("put", "get", "invalidate", "metric", "metrics"))
    parser.add_argument("--raw-key", default="shared-key")
    parser.add_argument("--school-id", type=int)
    parser.add_argument("--value", default="")
    parser.add_argument("--duration-ms", type=float, default=10.0)
    args = parser.parse_args()

    if args.command == "put":
        ok = await shared_set_json(
            "verification",
            args.raw_key,
            {"value": args.value},
            school_id=args.school_id,
            ttl_seconds=120,
        )
        result = {"ok": ok}
    elif args.command == "get":
        result = {
            "value": await shared_get_json(
                "verification",
                args.raw_key,
                args.school_id,
            )
        }
    elif args.command == "invalidate":
        result = {"version": await invalidate_shared_cache(args.school_id)}
    elif args.command == "metric":
        await record_chat_metric(
            duration_ms=args.duration_ms,
            route_mode="verify",
            cache_layers=["l2"],
            tool_count=1,
            strategy="answer",
        )
        result = {"ok": True}
    else:
        result = await metrics_snapshot()
    await close_redis()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
