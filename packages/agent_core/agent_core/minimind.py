from __future__ import annotations

import json
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .registry import SAFE_TOOLS
from .router import RuleRouter

INTENT_TO_TOOLS: dict[str, set[str]] = {
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


TOOL_PARAM_HELP: dict[str, tuple[str, ...]] = {
    "admissions_overview": ("year", "province", "major"),
    "source_overview": ("year",),
    "candidate_profile": ("year", "province", "major"),
    "subject_scores": ("year", "province", "major"),
    "major_choices": ("year", "major"),
    "medical_summary": ("year", "province", "major"),
    "forecast": ("year", "province", "major"),
    "official_admission_stats": ("year",),
    "major_alias_lookup": ("source_name", "query"),
    "anomaly_detection": ("year",),
    "plan_simulation": ("year", "major", "plan_delta"),
    "policy_faq": ("query",),
    "consultation_overview": ("year", "province"),
    "enrollment_funnel": ("year",),
    "score_band_statistics": ("year", "subject_name", "query"),
    "admissions_statistics": (
        "year", "province", "major", "subject_name", "batch_name", "plan_type_code",
        "gender_name", "source_school_name", "group_by", "metric", "choice_order_min",
        "choice_order_max", "top_n", "query",
    ),
}


def build_minimind_planner_prompt(fallback_intent: str) -> str:
    tools = sorted(INTENT_TO_TOOLS.get(fallback_intent, set()))
    catalog = "；".join(
        f"{name}({', '.join(TOOL_PARAM_HELP.get(name, ()))})"
        for name in tools
    )
    return (
        "你是招录智策受控工具规划器。只输出一个 JSON 对象，不输出解释或 Markdown。"
        "JSON 格式必须是 {\"tools\":[{\"name\":\"工具名\",\"params\":{}}]}。"
        f"当前意图：{fallback_intent}。允许工具：{catalog}。"
        "参数只能使用工具目录中列出的受控字段，不得自行扩展字段名。"
        "不得编造业务数字，不得选择未列出的工具，不得调用学生档案或学生统计工具。"
    )


@dataclass(slots=True)
class MiniMindConfig:
    enabled: bool = False
    base_url: str = ""
    model: str = "MiniMind-3"
    timeout_seconds: float = 3.0
    failure_threshold: int = 3
    reset_seconds: float = 60.0


def validate_minimind_params(
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


def parse_minimind_plan(
    content: str,
    *,
    message: str,
    fallback_intent: str,
    fallback_params: dict[str, Any],
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
        tool_params = validate_minimind_params(raw_params, message=message, fallback_params=fallback_params)
        if item["name"] == "plan_simulation" and not (tool_params.get("major") and tool_params.get("plan_delta") is not None):
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


class CircuitBreaker:
    def __init__(self, *, failure_threshold: int = 3, reset_seconds: float = 60.0) -> None:
        self.failure_threshold = max(1, failure_threshold)
        self.reset_seconds = max(1.0, reset_seconds)
        self._failures = 0
        self._opened_until = 0.0

    @property
    def available(self) -> bool:
        return time.monotonic() >= self._opened_until

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_until = time.monotonic() + self.reset_seconds
            self._failures = 0

    def record_success(self) -> None:
        self._failures = 0
        self._opened_until = 0.0


class MiniMindRouter:
    def __init__(
        self,
        config: MiniMindConfig,
        *,
        router: RuleRouter | None = None,
        post_json: Callable[[str, dict[str, Any], float], Awaitable[dict[str, Any]]] | None = None,
    ) -> None:
        self.config = config
        self.router = router or RuleRouter()
        self.post_json = post_json
        self.breaker = CircuitBreaker(
            failure_threshold=config.failure_threshold,
            reset_seconds=config.reset_seconds,
        )

    @property
    def configured(self) -> bool:
        return bool(self.config.enabled and self.config.base_url and self.post_json)

    async def route(self, message: str, *, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if not self.configured or not self.breaker.available:
            return None
        decision = self.router.route(message, context=context or {})
        if decision.intent not in INTENT_TO_TOOLS:
            return None
        payload = {
            "model": self.config.model,
            "stream": False,
            "temperature": 0,
            "max_tokens": 160,
            "messages": [
                {"role": "system", "content": build_minimind_planner_prompt(decision.intent)},
                {
                    "role": "user",
                    "content": f"问题：{message}\n规则已提取参数：{json.dumps(decision.params, ensure_ascii=False, default=str)}",
                },
            ],
        }
        try:
            data = await self.post_json(
                f"{self.config.base_url.rstrip('/')}/chat/completions",
                payload,
                self.config.timeout_seconds,
            )
            content = str(data["choices"][0]["message"]["content"]).strip()
            plan = parse_minimind_plan(
                content,
                message=message,
                fallback_intent=decision.intent,
                fallback_params=decision.params,
            )
            if plan:
                self.breaker.record_success()
            return plan
        except Exception:
            self.breaker.record_failure()
            return None
