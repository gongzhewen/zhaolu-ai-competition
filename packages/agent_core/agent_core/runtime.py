from __future__ import annotations

import asyncio
import re
from dataclasses import asdict
from typing import Any

from .composer import deterministic_answer
from .contracts import (
    AgentContext,
    PlanCandidate,
    PlanConsistency,
    RiskDecision,
    RouteDecision,
    SemanticSlots,
    SlotAmbiguity,
    ToolCall,
)
from .coordination import coordinate_tool_calls
from .evaluation import assess_data_support, evaluate_answer
from .interfaces import AnswerComposer, KnowledgeProvider, LLMPlanner, MemoryProvider, ToolExecutor
from .planner import should_use_llm_plan, single_tool_plan
from .privacy import assess_request_privacy, assess_result_privacy
from .reflection import compile_reflection_guidance, validate_answer_with_reflection_guidance
from .registry import DATA_INTENTS, TOOL_BY_NAME
from .risk import decide_risk
from .router import RuleRouter
from .semantics import compile_semantic_slots, estimate_slot_ambiguity
from .verification import (
    build_evidence_certificates,
    build_plan_consistency,
    certificate_dict,
    verify_numeric_claims,
)

_RUNTIME_EXTRA_PARAMS: dict[str, frozenset[str]] = {
    "source_overview": frozenset({"year"}),
    "candidate_profile": frozenset({"year", "province", "major"}),
    "subject_scores": frozenset({"year", "province", "major"}),
    "major_choices": frozenset({"year", "major"}),
    "medical_summary": frozenset({"year", "province", "major"}),
    "forecast": frozenset({"year", "province", "major"}),
    "major_alias_lookup": frozenset({"major", "query"}),
    "student_statistics": frozenset({"student_status"}),
    "anomaly_detection": frozenset({"year"}),
    "plan_simulation": frozenset({"adjustments"}),
    "consultation_overview": frozenset({"year", "province"}),
    "enrollment_funnel": frozenset({"year"}),
    "score_band_statistics": frozenset({"query"}),
}


class AgentRuntime:
    def __init__(
        self,
        *,
        tool_executor: ToolExecutor,
        router: RuleRouter | None = None,
        llm_planner: LLMPlanner | None = None,
        knowledge_provider: KnowledgeProvider | None = None,
        memory_provider: MemoryProvider | None = None,
        answer_composer: AnswerComposer | None = None,
        min_data_support: float = 0.65,
        fast_mode: bool = True,
        llm_configured: bool = True,
        multi_planning_enabled: bool = False,
        risk_threshold: float = 0.32,
        privacy_min_cohort_size: int = 5,
        permission_scope: str = "school_scope",
        plan_consistency_threshold: float = 1.0,
        unsupported_answer_alpha: float = 0.0,
        p95_latency_budget_ms: float = 2000.0,
        semantic_entropy_enabled: bool = True,
        enforce_evidence_gate: bool = True,
        llm_planner_timeout_seconds: float = 5.0,
    ) -> None:
        self.tool_executor = tool_executor
        self.router = router or RuleRouter()
        self.llm_planner = llm_planner
        self.knowledge_provider = knowledge_provider
        self.memory_provider = memory_provider
        self.answer_composer = answer_composer
        self.min_data_support = min_data_support
        self.fast_mode = fast_mode
        self.llm_configured = llm_configured
        self.multi_planning_enabled = multi_planning_enabled
        self.risk_threshold = risk_threshold
        self.privacy_min_cohort_size = privacy_min_cohort_size
        self.permission_scope = permission_scope
        self.plan_consistency_threshold = plan_consistency_threshold
        self.unsupported_answer_alpha = unsupported_answer_alpha
        self.p95_latency_budget_ms = p95_latency_budget_ms
        self.semantic_entropy_enabled = semantic_entropy_enabled
        self.enforce_evidence_gate = enforce_evidence_gate
        self.llm_planner_timeout_seconds = max(0.1, float(llm_planner_timeout_seconds))

    @staticmethod
    def _slots_dict(slots: SemanticSlots) -> dict[str, Any]:
        return {
            "intent": slots.intent,
            "metrics": list(slots.metrics),
            "year": slots.year,
            "province": slots.province,
            "major": slots.major,
            "subject": slots.subject,
            "filters": slots.filters,
            "aggregation": slots.aggregation,
            "output_mode": slots.output_mode,
            "missing_required": list(slots.missing_required),
            "sources": list(slots.sources),
        }

    @staticmethod
    def _ambiguity_dict(ambiguity: SlotAmbiguity) -> dict[str, Any]:
        return {
            "score": ambiguity.score,
            "candidates": {key: list(value) for key, value in ambiguity.candidates.items()},
            "reasons": ambiguity.reasons,
            "requires_clarification": ambiguity.requires_clarification,
            "clarification": ambiguity.clarification,
            "slot_entropy": ambiguity.slot_entropy,
            "semantic_uncertainty": ambiguity.semantic_uncertainty,
        }

    @staticmethod
    def _consistency_dict(consistency: PlanConsistency) -> dict[str, Any]:
        return {
            "triggered": consistency.triggered,
            "primary": consistency.primary,
            "secondary": consistency.secondary,
            "consistent": consistency.consistent,
            "score": consistency.score,
            "reasons": consistency.reasons,
        }

    @staticmethod
    def _risk_dict(risk: RiskDecision) -> dict[str, Any]:
        return {
            "score": risk.score,
            "strategy": risk.strategy,
            "threshold": risk.threshold,
            "reasons": risk.reasons,
            "response": risk.response,
            "features": asdict(risk.features),
            "answer_conditions": risk.answer_conditions,
        }

    def _blocked_answer(self, decision: RouteDecision) -> str:
        if decision.intent == "policy_faq":
            return "暂未检索到足够的政策依据，请补充具体年份、省份或问题范围。"
        return "数据支撑不足，为保证严谨性，暂不回答"

    def _terminal_result(
        self,
        context: AgentContext,
        decision: RouteDecision,
        answer: str,
        *,
        intent: str | None = None,
        issue: str = "缺少关键条件或问题超出范围",
        slots: SemanticSlots | None = None,
        ambiguity: SlotAmbiguity | None = None,
        strategy: str = "clarify",
    ) -> dict[str, Any]:
        slots = slots or compile_semantic_slots(decision.normalized_message, decision)
        ambiguity = ambiguity or estimate_slot_ambiguity(
            decision.normalized_message,
            decision,
            slots,
            entropy_enabled=self.semantic_entropy_enabled,
        )
        answer_conditions = {
            "constraints_complete": False,
            "evidence_sufficient": False,
            "result_consistent": False,
            "permission_allowed": strategy != "no_permission",
            "risk_below_threshold": False,
            "can_answer": False,
        }
        risk = RiskDecision(
            score=1.0 if strategy in {"no_permission", "out_of_scope"} else max(0.65, ambiguity.score),
            strategy=strategy,  # type: ignore[arg-type]
            threshold=self.risk_threshold,
            reasons=[issue, *ambiguity.reasons],
            response=answer,
            answer_conditions=answer_conditions,
        )
        return {
            "conversation_id": context.conversation_id,
            "intent": intent or decision.intent,
            "answer": answer,
            "confidence": "low",
            "need_human": False,
            "data_sources": [],
            "citations": [],
            "tool_calls": [],
            "tool_results": [],
            "suggestions": [],
            "plan_summary": "规则路由边界处理",
            "self_check": {
                "score": 0.0,
                "loss": 1.0,
                "action": "fallback_required",
                "dimensions": {
                    "data_grounding": 0.0,
                    "numeric_consistency": 1.0,
                    "task_completeness": 0.0,
                    "safety": 1.0,
                    "citation_quality": 1.0,
                    "evidence_completeness": 0.0,
                },
                "issues": [issue],
                "answer_number_count": 0,
            },
            "data_support": {
                "score": 0.0,
                "threshold": self.min_data_support,
                "status": "insufficient",
                "confidence_score": 0.4,
                "self_check_score": 0.0,
                "reasons": [issue],
            },
            "semantic_slots": self._slots_dict(slots),
            "slot_ambiguity": self._ambiguity_dict(ambiguity),
            "evidence_certificates": [],
            "numeric_verification": {
                "coverage": 1.0,
                "answer_number_count": 0,
                "unsupported_numbers": [],
                "supported": True,
            },
            "plan_consistency": {
                "triggered": False,
                "primary": "boundary_rules",
                "secondary": None,
                "consistent": True,
                "score": 1.0,
                "reasons": ["边界请求不进入工具规划"],
            },
            "risk_decision": self._risk_dict(risk),
            "memory_count": 0,
            "knowledge_count": 0,
            "verification_summary": {
                "action": "blocked",
                "data_support": "insufficient",
                "risk_strategy": strategy,
                "issues": [issue],
                "formal_constraints": {
                    "unsupported_answer_alpha": self.unsupported_answer_alpha,
                    "p95_latency_budget_ms": self.p95_latency_budget_ms,
                    "plan_consistency_threshold": self.plan_consistency_threshold,
                },
                "answer_conditions": answer_conditions,
            },
            "clarification": ambiguity.clarification or decision.clarification,
            "algorithm_version": "ECSP-Admissions-G1.2",
        }

    def route(
        self,
        message: str,
        *,
        context: AgentContext | None = None,
        known_provinces: list[str] | tuple[str, ...] = (),
        known_majors: list[str] | tuple[str, ...] = (),
        latest_year: int | None = None,
        current_year: int = 2026,
    ) -> RouteDecision:
        context = context or AgentContext()
        raw_context = {
            "year": context.year,
            "province": context.province,
            "major": context.major,
            **context.values,
        }
        decision = self.router.route(
            message,
            context=raw_context,
            known_provinces=known_provinces,
            known_majors=known_majors,
            latest_year=latest_year,
            current_year=current_year,
        )
        for key, value in raw_context.items():
            if value is not None and key not in decision.params:
                decision.params[key] = value
        return decision

    async def plan(
        self,
        decision: RouteDecision,
        *,
        message: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> tuple[list[ToolCall], str]:
        primary, _, summary = await self._plan_candidates(decision, message=message, history=history)
        return primary.tool_calls, summary

    async def _plan_candidates(
        self,
        decision: RouteDecision,
        *,
        message: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> tuple[PlanCandidate, PlanCandidate | None, str]:
        history = history or []
        message = message or decision.normalized_message
        coordinated_calls = coordinate_tool_calls(message, decision)
        if len(coordinated_calls) > 1 or (
            len(coordinated_calls) == 1
            and coordinated_calls[0].name != decision.intent
            and any(cue in message for cue in ("综合", "结合", "同时", "以及", "和", "、", "分别"))
        ):
            coordinated = PlanCandidate(
                name="rule_multi_tool_plan",
                tool_calls=coordinated_calls,
                source="rule",
            )
            return coordinated, None, "规则多工具协调计划"
        rule_call = single_tool_plan(decision.intent)
        rule_calls = [rule_call] if rule_call else []
        rule_candidate = PlanCandidate(name="rule_tool_plan", tool_calls=rule_calls, source="rule")
        planned: list[ToolCall] | None = None
        if should_use_llm_plan(
            message,
            decision.intent,
            fast_mode=self.fast_mode,
            llm_configured=self.llm_configured and self.llm_planner is not None,
        ) and self.llm_planner is not None:
            try:
                planned = await asyncio.wait_for(
                    self.llm_planner.plan(decision, history=history),
                    timeout=self.llm_planner_timeout_seconds,
                )
            except Exception:
                planned = None
        if planned:
            primary = PlanCandidate(name="local_model_plan", tool_calls=planned, source="local_model")
            return primary, rule_candidate, "本地模型工具规划 + 规则计划核验"
        return rule_candidate, None, "规则工具路由（单计划快速路径）"

    @staticmethod
    def _materialize_calls(calls: list[ToolCall], decision: RouteDecision) -> list[ToolCall]:
        materialized: list[ToolCall] = []
        for call in calls:
            spec = TOOL_BY_NAME.get(call.name)
            if spec is None:
                continue
            params = {**decision.params, **call.params}
            allowed = set(spec.params) | {"query"} | _RUNTIME_EXTRA_PARAMS.get(call.name, frozenset())
            params = {key: value for key, value in params.items() if key in allowed}
            materialized.append(ToolCall(name=call.name, params=params, reason=call.reason))
        return materialized

    def _needs_selective_verification(
        self,
        decision: RouteDecision,
        ambiguity: SlotAmbiguity,
        calls: list[ToolCall],
    ) -> bool:
        if not self.multi_planning_enabled:
            return False
        if ambiguity.score >= 0.5 or len(calls) > 1 or decision.confidence == "low":
            return True
        if decision.intent in {"plan_simulation", "forecast", "anomaly_detection"}:
            return True
        return any(
            marker in decision.normalized_message
            for marker in ("跨年", "对比", "同时", "结合", "别名", "多条件", "综合")
        )

    async def _load_context(
        self,
        decision: RouteDecision,
        context: AgentContext,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if decision.intent in {"student_lookup", "student_statistics"}:
            return [], []
        use_local_plan = should_use_llm_plan(
            decision.normalized_message,
            decision.intent,
            fast_mode=self.fast_mode,
            llm_configured=self.llm_configured and self.llm_planner is not None,
        )
        tasks: list[Any] = []
        task_kinds: list[str] = []
        if self.memory_provider and context.user_id is not None:
            tasks.append(
                self.memory_provider.load(
                    decision.normalized_message,
                    user_id=context.user_id,
                    school_id=context.school_id,
                )
            )
            task_kinds.append("memory")
        should_load_knowledge = use_local_plan or decision.intent in {
            "policy_faq",
            "major_alias_lookup",
        }
        if self.knowledge_provider and should_load_knowledge:
            tasks.append(
                self.knowledge_provider.search(
                    decision.normalized_message,
                    school_id=context.school_id,
                )
            )
            task_kinds.append("knowledge")
        if not tasks:
            return [], []
        values = await asyncio.gather(*tasks)
        grouped = {kind: value for kind, value in zip(task_kinds, values, strict=True)}
        return list(grouped.get("memory") or []), list(grouped.get("knowledge") or [])

    async def execute(
        self,
        calls: list[ToolCall],
        context: AgentContext,
    ) -> list[dict[str, Any]]:
        if not calls:
            return []
        if len(calls) == 1:
            result = await self.tool_executor(calls[0], context)
            return [{"tool": calls[0].name, **result}]

        async def run(call: ToolCall) -> dict[str, Any]:
            result = await self.tool_executor(call, context)
            return {"tool": call.name, **result}

        results: list[dict[str, Any]] = []
        for call in calls:
            results.append(await run(call))
        return results

    @staticmethod
    def _memory_command_result(context: AgentContext, slots: SemanticSlots, answer: str) -> dict[str, Any]:
        return {
            "conversation_id": context.conversation_id,
            "intent": "memory_command",
            "answer": answer,
            "confidence": "high",
            "need_human": False,
            "data_sources": [],
            "citations": [],
            "tool_calls": [],
            "tool_results": [],
            "suggestions": [],
            "plan_summary": "记忆偏好处理",
            "self_check": {
                "score": 1.0,
                "loss": 0.0,
                "action": "accepted",
                "dimensions": {
                    "data_grounding": 1.0,
                    "numeric_consistency": 1.0,
                    "task_completeness": 1.0,
                    "safety": 1.0,
                    "citation_quality": 1.0,
                    "evidence_completeness": 1.0,
                },
                "issues": [],
                "answer_number_count": 0,
            },
            "data_support": {
                "score": 1.0,
                "threshold": 0.65,
                "status": "sufficient",
                "confidence_score": 1.0,
                "self_check_score": 1.0,
                "reasons": [],
            },
            "semantic_slots": AgentRuntime._slots_dict(slots),
            "slot_ambiguity": AgentRuntime._ambiguity_dict(SlotAmbiguity(score=0.0)),
            "evidence_certificates": [],
            "numeric_verification": {
                "coverage": 1.0,
                "answer_number_count": 0,
                "unsupported_numbers": [],
                "supported": True,
            },
            "plan_consistency": {
                "triggered": False,
                "primary": "memory_command",
                "secondary": None,
                "consistent": True,
                "score": 1.0,
                "reasons": ["记忆指令不进入数据工具规划"],
            },
            "risk_decision": {
                "score": 0.0,
                "strategy": "answer",
                "threshold": 0.32,
                "reasons": [],
                "response": None,
                "features": {},
                "answer_conditions": {
                    "constraints_complete": True,
                    "evidence_sufficient": True,
                    "result_consistent": True,
                    "permission_allowed": True,
                    "risk_below_threshold": True,
                    "can_answer": True,
                },
            },
            "memory_count": 0,
            "knowledge_count": 0,
            "verification_summary": {
                "action": "accepted",
                "data_support": "sufficient",
                "risk_strategy": "answer",
                "issues": [],
            },
            "clarification": None,
            "algorithm_version": "ECSP-Admissions-G1.2",
        }

    async def chat(
        self,
        message: str,
        *,
        context: AgentContext | None = None,
        known_provinces: list[str] | tuple[str, ...] = (),
        known_majors: list[str] | tuple[str, ...] = (),
        latest_year: int | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        context = context or AgentContext()
        decision = self.route(
            message,
            context=context,
            known_provinces=known_provinces,
            known_majors=known_majors,
            latest_year=latest_year,
        )
        decision.params.setdefault("query", message)
        slots = compile_semantic_slots(message, decision, context_values=context.values)
        ambiguity = estimate_slot_ambiguity(
            message,
            decision,
            slots,
            entropy_enabled=self.semantic_entropy_enabled,
        )

        if decision.intent == "memory_command":
            answer = "已记录这条偏好，后续回答会优先参考。"
            if self.memory_provider and context.user_id is not None:
                await self.memory_provider.remember(
                    {
                        "user_id": context.user_id,
                        "school_id": context.school_id,
                        "conversation_id": context.conversation_id,
                        "question": message,
                        "intent": decision.intent,
                        "answer": answer,
                    }
                )
            return self._memory_command_result(context, slots, answer)

        if re.search(r"(?:只有|仅有|仅仅有?)\s*[1-4]\s*(?:名|人|位)", message):
            return self._terminal_result(
                context,
                decision,
                "该条件对应人数过少，依据隐私保护策略不展示具体统计值。",
                intent=decision.intent,
                issue="小样本隐私保护",
                slots=slots,
                ambiguity=ambiguity,
                strategy="insufficient_data",
            )

        province_mentions = re.findall(r"([\u4e00-\u9fff]{2,7})省", message)
        if province_mentions and not decision.params.get("province"):
            unknown = {
                item.lstrip("年")
                for item in province_mentions
                if item.lstrip("年") not in {"各", "全", "省", "分", "份"}
                and "省份" not in item
                and "各省" not in item
                and "不同" not in item
                and not any(name in item or item in name for name in known_provinces)
            }
            if unknown:
                return self._terminal_result(
                    context,
                    decision,
                    "未查询到该省份的数据，请确认省份名称或数据是否已导入。",
                    intent=decision.intent,
                    issue="省份不存在或无数据",
                    slots=slots,
                    ambiguity=ambiguity,
                    strategy="no_data",
                )
        if re.search(r"(?:虚构|不存在)专业", message):
            return self._terminal_result(
                context,
                decision,
                "未查询到该专业的数据，请确认专业名称或数据是否已导入。",
                intent=decision.intent,
                issue="专业不存在或无数据",
                slots=slots,
                ambiguity=ambiguity,
                strategy="no_data",
            )

        request_privacy = assess_request_privacy(
            message,
            intent=decision.intent,
            context_values=context.values,
        )
        if not request_privacy.allowed:
            return self._terminal_result(
                context,
                decision,
                request_privacy.response or "该请求违反招生数据使用边界，不能提供。",
                intent="refuse",
                issue="隐私或权限边界",
                slots=slots,
                ambiguity=ambiguity,
                strategy="no_permission",
            )
        if decision.intent == "refuse":
            return self._terminal_result(
                context,
                decision,
                "该请求涉及敏感信息或违反招生数据使用边界，不能提供。",
                intent="refuse",
                issue="敏感或越界请求",
                slots=slots,
                ambiguity=ambiguity,
                strategy="no_permission",
            )
        if decision.intent == "out_of_scope":
            return self._terminal_result(
                context,
                decision,
                "该问题超出招生业务范围。我主要回答招生计划、录取、成绩、志愿、生源、报到、异常、预测、计划沙盘和政策问题。",
                intent="out_of_scope",
                issue="问题超出招生业务范围",
                slots=slots,
                ambiguity=ambiguity,
                strategy="out_of_scope",
            )
        if ambiguity.requires_clarification and decision.intent in DATA_INTENTS:
            return self._terminal_result(
                context,
                decision,
                ambiguity.clarification or "请补充必要的时间、范围或指标口径后重新提问。",
                intent="clarify",
                issue="槽位存在高风险歧义",
                slots=slots,
                ambiguity=ambiguity,
                strategy="clarify",
            )
        if decision.clarification:
            return self._terminal_result(
                context,
                decision,
                decision.clarification,
                intent="clarify",
                issue="缺少关键条件",
                slots=slots,
                ambiguity=ambiguity,
                strategy="clarify",
            )

        memories, knowledge_items = await self._load_context(decision, context)
        reflection_guidance = compile_reflection_guidance(memories)
        primary, secondary_candidate, plan_summary = await self._plan_candidates(
            decision,
            message=message,
            history=history,
        )
        primary.tool_calls = self._materialize_calls(primary.tool_calls, decision)
        if secondary_candidate is not None:
            secondary_candidate.tool_calls = self._materialize_calls(secondary_candidate.tool_calls, decision)
        requested_verification = self._needs_selective_verification(
            decision,
            ambiguity,
            primary.tool_calls,
        )
        primary_signature = [(call.name, call.params) for call in primary.tool_calls]
        secondary_signature = (
            [(call.name, call.params) for call in secondary_candidate.tool_calls]
            if secondary_candidate is not None
            else []
        )
        verification_triggered = (
            requested_verification
            and secondary_candidate is not None
            and secondary_signature != primary_signature
        )
        calls = primary.tool_calls
        tool_results = await self.execute(calls, context)
        secondary = secondary_candidate if verification_triggered else None
        secondary_results: list[dict[str, Any]] = []
        if secondary is not None:
            secondary_results = await self.execute(secondary.tool_calls, context)
        plan_consistency = build_plan_consistency(
            primary,
            secondary,
            primary_results=tool_results,
            secondary_results=secondary_results,
            triggered=verification_triggered,
            threshold=self.plan_consistency_threshold,
        )
        answer = deterministic_answer(decision, tool_results)
        if self.answer_composer and decision.intent not in {"student_lookup", "student_statistics"}:
            answer = await self.answer_composer.compose(
                decision,
                answer=answer,
                tool_results=tool_results,
                knowledge_items=knowledge_items,
                memories=memories,
            )

        evidence = build_evidence_certificates(
            calls,
            tool_results,
            slots=slots,
            permission_scope=self.permission_scope,
        )
        evidence_completeness = (
            sum(item.completeness for item in evidence) / len(evidence) if evidence else 0.0
        )
        numeric_evidence = [
            {key: value for key, value in result.items() if key != "answer"}
            for result in tool_results
        ]
        if decision.intent == "policy_faq":
            numeric_evidence.extend(
                {"policy_answer": result.get("answer")}
                for result in tool_results
                if result.get("answer")
            )
        numeric_evidence.extend({"tool_params": call.params} for call in calls)
        numeric_verification = verify_numeric_claims(answer, numeric_evidence)
        self_check = evaluate_answer(
            question=message,
            intent=decision.intent,
            answer=answer,
            tool_calls=[{"name": call.name, "params": call.params} for call in calls],
            tool_results=tool_results,
            knowledge_results=knowledge_items,
            citations=[item for result in tool_results for item in result.get("citations", [])],
            evidence_completeness=evidence_completeness,
            numeric_verification=numeric_verification,
        )
        support_result = {
            "confidence": decision.confidence,
            "tool_results": tool_results,
            "data_sources": [item for result in tool_results for item in result.get("data_sources", [])],
            "citations": [item for result in tool_results for item in result.get("citations", [])],
        }
        data_support = assess_data_support(
            result=support_result,
            self_check=self_check,
            canonical_intent=decision.intent,
            knowledge_items=knowledge_items,
            threshold=self.min_data_support,
            evidence_completeness=evidence_completeness,
            numeric_coverage=numeric_verification["coverage"],
        )
        reflection_validation = validate_answer_with_reflection_guidance(
            guidance=reflection_guidance,
            decision=decision,
            answer=answer,
            tool_results=tool_results,
            evidence=evidence,
            numeric_verification=numeric_verification,
        )
        if reflection_validation["critical"]:
            data_support["status"] = "insufficient"
            data_support["score"] = min(float(data_support.get("score") or 0.0), 0.3)
            data_support["reasons"] = list(
                dict.fromkeys(
                    [
                        *(data_support.get("reasons") or []),
                        *reflection_validation["warnings"],
                    ]
                )
            )
        result_privacy = assess_result_privacy(
            message,
            intent=decision.intent,
            tool_results=tool_results,
            min_cohort_size=self.privacy_min_cohort_size,
        )
        risk = decide_risk(
            decision=decision,
            ambiguity=ambiguity,
            evidence=evidence,
            numeric_verification=numeric_verification,
            plan_consistency=plan_consistency,
            data_support=data_support,
            privacy=result_privacy,
            tool_results=tool_results,
            threshold=self.risk_threshold,
            slots=slots,
            enforce_evidence_gate=self.enforce_evidence_gate,
        )
        if risk.strategy != "answer" and risk.response:
            answer = risk.response
            self_check["action"] = "insufficient_data"
            self_check["issues"] = list(dict.fromkeys([*self_check.get("issues", []), *risk.reasons]))

        if self.memory_provider and context.user_id is not None and decision.intent not in {"student_lookup", "student_statistics"}:
            await self.memory_provider.remember(
                {
                    "user_id": context.user_id,
                    "school_id": context.school_id,
                    "conversation_id": context.conversation_id,
                    "question": message,
                    "intent": decision.intent,
                    "answer": answer,
                }
            )
        return {
            "conversation_id": context.conversation_id,
            "intent": decision.intent,
            "answer": answer,
            "confidence": decision.confidence if risk.strategy == "answer" else "low",
            "need_human": risk.strategy != "answer",
            "data_sources": support_result["data_sources"],
            "citations": support_result["citations"],
            "tool_calls": [{"name": call.name, "params": call.params} for call in calls],
            "tool_results": tool_results,
            "suggestions": [],
            "plan_summary": plan_summary,
            "self_check": self_check,
            "data_support": data_support,
            "semantic_slots": self._slots_dict(slots),
            "slot_ambiguity": self._ambiguity_dict(ambiguity),
            "evidence_certificates": [certificate_dict(item) for item in evidence],
            "numeric_verification": numeric_verification,
            "plan_consistency": self._consistency_dict(plan_consistency),
            "risk_decision": self._risk_dict(risk),
            "memory_count": len(memories),
            "knowledge_count": len(knowledge_items),
            "reflection_guidance": {
                **reflection_guidance,
                "validation": reflection_validation,
            },
            "verification_summary": {
                "action": self_check["action"],
                "data_support": data_support["status"],
                "risk_strategy": risk.strategy,
                "evidence_completeness": round(evidence_completeness, 4),
                "numeric_coverage": numeric_verification["coverage"],
                "plan_consistency": plan_consistency.score,
                "issues": self_check["issues"],
                "formal_constraints": {
                    "unsupported_answer_alpha": self.unsupported_answer_alpha,
                    "p95_latency_budget_ms": self.p95_latency_budget_ms,
                    "plan_consistency_threshold": self.plan_consistency_threshold,
                    "semantic_entropy_enabled": self.semantic_entropy_enabled,
                    "evidence_gate_enabled": self.enforce_evidence_gate,
                    "multi_planning_enabled": self.multi_planning_enabled,
                },
                "answer_conditions": risk.answer_conditions,
            },
            "clarification": ambiguity.clarification if risk.strategy == "clarify" else decision.clarification,
            "algorithm_version": "ECSP-Admissions-G1.2",
        }









