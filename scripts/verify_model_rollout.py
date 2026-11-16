from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.modules.ai_gateway.minimind_router import (
    MiniMindRouter,
    ModelEndpoint,
    ModelRolloutConfig,
)


def valid_response(model: str) -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"tools":[{"name":"admissions_overview",'
                        '"params":{"year":2026}}]}'
                    )
                }
            }
        ],
        "model": model,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/G9/model_rollout_20261110.json")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--stable-base-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--stable-model", default="qwen2.5-coder-3b")
    parser.add_argument("--invalid-canary-url", default="http://127.0.0.1:9/v1")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)

    original_enabled = settings.minimind_enabled
    original_redis = settings.redis_enabled
    settings.minimind_enabled = True
    settings.redis_enabled = False
    stable = (
        ModelEndpoint("stable", args.stable_base_url, args.stable_model)
        if args.live
        else ModelEndpoint("stable", "http://stable.local/v1", "stable-model")
    )
    canary = (
        ModelEndpoint("canary", args.stable_base_url, args.stable_model)
        if args.live
        else ModelEndpoint("canary", "http://canary.local/v1", "canary-model")
    )
    request = {
        "message": "2026年招生多少人",
        "fallback_intent": "admissions_overview",
        "params": {"year": 2026},
    }
    try:
        async def healthy_post(url: str, payload: dict, _timeout: float) -> dict:
            return valid_response(str(payload["model"]))

        healthy_router = MiniMindRouter(
            rollout=ModelRolloutConfig(stable, canary, 100),
            post_json=None if args.live else healthy_post,
        )
        canary_plan = await healthy_router.route(**request)

        async def failing_canary_post(url: str, payload: dict, _timeout: float) -> dict:
            if "canary.local" in url:
                raise TimeoutError("simulated canary timeout")
            return valid_response(str(payload["model"]))

        invalid_canary = ModelEndpoint(
            "canary",
            args.invalid_canary_url,
            args.stable_model if args.live else "canary-model",
        )
        failover_router = MiniMindRouter(
            rollout=ModelRolloutConfig(stable, invalid_canary, 100),
            post_json=None if args.live else failing_canary_post,
        )
        failover_plan = await failover_router.route(**request)

        rollback_router = MiniMindRouter(
            rollout=ModelRolloutConfig(stable, canary, 0),
            post_json=None if args.live else healthy_post,
        )
        rollback_plan = await rollback_router.route(**request)
    finally:
        settings.minimind_enabled = original_enabled
        settings.redis_enabled = original_redis

    result = {
        "evaluation_kind": "model_canary_and_rollback_drill",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "simulation_only": not args.live,
        "network_endpoint_used": args.live,
        "stable_endpoint": stable.base_url if args.live else None,
        "stable_model": stable.model if args.live else None,
        "steps": {
            "canary_100_percent": {
                "status": "passed" if canary_plan and canary_plan.get("model_version") == "canary" else "failed",
                "model_version": canary_plan.get("model_version") if canary_plan else None,
            },
            "canary_failure_auto_fallback": {
                "status": (
                    "passed"
                    if failover_plan
                    and failover_plan.get("model_version") == "stable"
                    and failover_plan.get("fallback_from") == "canary"
                    else "failed"
                ),
                "model_version": failover_plan.get("model_version") if failover_plan else None,
                "fallback_from": failover_plan.get("fallback_from") if failover_plan else None,
            },
            "rollback_to_stable": {
                "status": "passed" if rollback_plan and rollback_plan.get("model_version") == "stable" else "failed",
                "model_version": rollback_plan.get("model_version") if rollback_plan else None,
            },
        },
        "boundary": (
            "本演练验证版本选择、失败回退和回滚配置；"
            "不代表真实灰度模型的业务准确率或生产网络故障恢复。"
        ),
    }
    all_passed = all(step["status"] == "passed" for step in result["steps"].values())
    result["status"] = "passed" if all_passed else "failed"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not all_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
