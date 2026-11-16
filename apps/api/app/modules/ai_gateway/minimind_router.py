from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
from agent_core.minimind import build_minimind_planner_prompt
from app.core.config import settings
from app.core.runtime_metrics import record_llm_metric

logger = logging.getLogger(__name__)

SAFE_TOOLS = {
    "admissions_overview",
    "source_overview",
    "candidate_profile",
    "subject_scores",
    "major_choices",
    "medical_summary",
    "forecast",
    "official_admission_stats",
    "major_alias_lookup",
    "anomaly_detection",
    "plan_simulation",
    "policy_faq",
    "consultation_overview",
    "enrollment_funnel",
    "score_band_statistics",
    "admissions_statistics",
}

INTENT_TO_TOOLS = {
    "admissions_overview": {"admissions_overview"},
    "source_overview": {"source_overview"},
    "candidate_profile": {"candidate_profile"},
    "subject_scores": {"subject_scores"},
    "major_choices": {"major_choices"},
    "medical_summary": {"medical_summary"},
    "forecast": {"forecast", "admissions_overview"},
    "official_admission_stats": {"official_admission_stats"},
    "major_alias_lookup": {"major_alias_lookup"},
    "anomaly_detection": {"anomaly_detection"},
    "plan_simulation": {"plan_simulation"},
    "policy_faq": {"policy_faq"},
    "consultation_overview": {"consultation_overview"},
    "enrollment_funnel": {"enrollment_funnel"},
    "score_band_statistics": {"score_band_statistics"},
    "admissions_statistics": {"admissions_statistics"},
}


@dataclass(frozen=True, slots=True)
class ModelEndpoint:
    version_id: str
    base_url: str
    model: str


@dataclass(frozen=True, slots=True)
class ModelRolloutConfig:
    stable: ModelEndpoint
    canary: ModelEndpoint | None
    canary_percent: int

    def select(self, message: str, params: dict[str, Any]) -> ModelEndpoint:
        if self.canary is None or self.canary_percent <= 0:
            return self.stable
        percent = min(100, max(0, self.canary_percent))
        payload = json.dumps(
            {"message": message, "params": params},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        bucket = int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8], 16) % 100
        return self.canary if bucket < percent else self.stable


def build_model_rollout_config() -> ModelRolloutConfig:
    raw: dict[str, Any] = {}
    try:
        parsed = json.loads(settings.minimind_model_versions or "{}")
        if isinstance(parsed, dict):
            raw = parsed
    except json.JSONDecodeError:
        raw = {}

    def endpoint(version_name: str, fallback_model: str) -> ModelEndpoint | None:
        item = raw.get(version_name)
        if not isinstance(item, dict):
            if version_name != settings.minimind_stable_version:
                return None
            item = {}
        base_url = str(item.get("base_url") or settings.minimind_base_url or "").strip()
        model = str(item.get("model") or fallback_model or "").strip()
        if not base_url or not model:
            return None
        return ModelEndpoint(
            version_id=version_name,
            base_url=base_url.rstrip("/"),
            model=model,
        )

    stable = endpoint(settings.minimind_stable_version, settings.minimind_model)
    if stable is None:
        stable = ModelEndpoint(
            version_id=settings.minimind_stable_version,
            base_url=str(settings.minimind_base_url or "").rstrip("/"),
            model=settings.minimind_model,
        )
    canary = endpoint(settings.minimind_canary_version, settings.minimind_model)
    if canary is not None and canary.version_id == stable.version_id:
        canary = None
    return ModelRolloutConfig(
        stable=stable,
        canary=canary,
        canary_percent=min(100, max(0, settings.minimind_canary_percent)),
    )


class MiniMindRouter:
    def __init__(
        self,
        *,
        rollout: ModelRolloutConfig | None = None,
        post_json: Callable[[str, dict[str, Any], float], Awaitable[dict[str, Any]]] | None = None,
    ) -> None:
        self.rollout = rollout or build_model_rollout_config()
        self.post_json = post_json
        self._failures: dict[str, int] = {}
        self._opened_until: dict[str, float] = {}

    @property
    def configured(self) -> bool:
        return bool(
            settings.minimind_enabled
            and self.rollout.stable.base_url
            and self.rollout.stable.model
        )

    def _available(self, endpoint: ModelEndpoint) -> bool:
        if not settings.minimind_enabled or not endpoint.base_url or not endpoint.model:
            return False
        return time.monotonic() >= self._opened_until.get(endpoint.version_id, 0.0)

    def _record_failure(self, endpoint: ModelEndpoint) -> None:
        failures = self._failures.get(endpoint.version_id, 0) + 1
        if failures >= max(1, settings.minimind_failure_threshold):
            self._opened_until[endpoint.version_id] = (
                time.monotonic() + max(1, settings.minimind_reset_seconds)
            )
            failures = 0
        self._failures[endpoint.version_id] = failures

    def _record_success(self, endpoint: ModelEndpoint) -> None:
        self._failures[endpoint.version_id] = 0
        self._opened_until[endpoint.version_id] = 0.0

    async def route(
        self,
        *,
        message: str,
        fallback_intent: str,
        params: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self.configured or fallback_intent not in INTENT_TO_TOOLS:
            return None

        selected = self.rollout.select(message, params)
        candidates = [selected]
        if selected.version_id != self.rollout.stable.version_id:
            candidates.append(self.rollout.stable)
        for index, endpoint in enumerate(candidates):
            if not self._available(endpoint):
                continue
            plan = await self._route_endpoint(
                endpoint,
                message=message,
                fallback_intent=fallback_intent,
                params=params,
            )
            if plan:
                if index > 0:
                    plan["fallback_from"] = selected.version_id
                return plan
        return None

    async def _route_endpoint(
        self,
        endpoint: ModelEndpoint,
        *,
        message: str,
        fallback_intent: str,
        params: dict[str, Any],
    ) -> dict[str, Any] | None:
        payload = {
            "model": endpoint.model,
            "stream": False,
            "temperature": 0,
            "max_tokens": 160,
            "messages": [
                {
                    "role": "system",
                    "content": build_minimind_planner_prompt(fallback_intent),
                },
                {
                    "role": "user",
                    "content": f"问题：{message}\n规则已提取参数：{json.dumps(params, ensure_ascii=False, default=str)}",
                },
            ],
        }
        started = time.perf_counter()
        try:
            if self.post_json is not None:
                data = await self.post_json(
                    f"{endpoint.base_url}/chat/completions",
                    payload,
                    settings.minimind_timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(timeout=settings.minimind_timeout_seconds) as client:
                    response = await client.post(
                        f"{endpoint.base_url}/chat/completions",
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
            plan = self._parse_and_validate(
                content=content,
                message=message,
                fallback_intent=fallback_intent,
                params=params,
            )
            status = "success" if plan else "rejected"
            await record_llm_metric(
                kind="minimind",
                status=status,
                duration_ms=(time.perf_counter() - started) * 1000,
                version=endpoint.version_id,
            )
            if plan:
                self._record_success(endpoint)
                plan["model_version"] = endpoint.version_id
            return plan
        except httpx.TimeoutException:
            self._record_failure(endpoint)
            await record_llm_metric(
                kind="minimind",
                status="timeout",
                duration_ms=(time.perf_counter() - started) * 1000,
                version=endpoint.version_id,
            )
            return None
        except Exception as exc:  # noqa: BLE001 - any endpoint/parse failure must fail over
            self._record_failure(endpoint)
            await record_llm_metric(
                kind="minimind",
                status="error",
                duration_ms=(time.perf_counter() - started) * 1000,
                version=endpoint.version_id,
            )
            logger.info(
                "MiniMind endpoint %s unavailable, trying next candidate: %s",
                endpoint.version_id,
                exc,
            )
            return None

    def _parse_and_validate(
        self,
        *,
        content: str,
        message: str,
        fallback_intent: str,
        params: dict[str, Any],
    ) -> dict[str, Any] | None:
        cleaned = re.sub(r"^```(?:json)?\s*", "", content.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            candidate = json.loads(cleaned)
        except json.JSONDecodeError:
            return None
        if not isinstance(candidate, dict) or not isinstance(candidate.get("tools"), list):
            return None

        allowed_tools = INTENT_TO_TOOLS.get(fallback_intent, set())
        tools: list[dict[str, Any]] = []
        for item in candidate["tools"][:2]:
            if not isinstance(item, dict) or item.get("name") not in allowed_tools:
                continue
            if item.get("name") not in SAFE_TOOLS:
                continue
            raw_params = item.get("params") if isinstance(item.get("params"), dict) else {}
            tool_params = self._validated_params(raw_params, message=message, fallback_params=params)
            if item["name"] == "plan_simulation" and not (
                tool_params.get("major") and tool_params.get("plan_delta") is not None
            ):
                continue
            tools.append({"name": item["name"], "params": tool_params})

        if not tools:
            return None
        if tools[0]["name"] != fallback_intent and fallback_intent not in {"forecast"}:
            return None
        return {
            "intent": fallback_intent,
            "tools": tools,
            "reason": "MiniMind 本地语言路由",
            "suggestions": [],
        }

    @staticmethod
    def _validated_params(
        raw_params: dict[str, Any],
        *,
        message: str,
        fallback_params: dict[str, Any],
    ) -> dict[str, Any]:
        allowed = {"year", "province", "major", "plan_delta", "source_name", "query", "subject_name", "batch_name", "plan_type_code", "gender_name", "source_school_name", "group_by", "metric", "choice_order_min", "choice_order_max", "top_n"}
        result: dict[str, Any] = {}
        for key, value in raw_params.items():
            if key not in allowed or value is None:
                continue
            if key in {"year", "plan_delta"}:
                try:
                    result[key] = int(value)
                except (TypeError, ValueError):
                    continue
            elif key in {"province", "major", "source_name"}:
                text_value = str(value).strip()
                if not text_value or text_value not in message:
                    continue
                result[key] = text_value
            else:
                result[key] = value

        for key in ("year", "province", "major", "plan_delta"):
            if fallback_params.get(key) is not None:
                result[key] = fallback_params[key]
        if result.get("source_name") is None and result.get("major"):
            result.pop("source_name", None)
        return result


minimind_router = MiniMindRouter()

