from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_PRIVATE_FIELDS = ("手机号", "身份证", "家庭住址", "联系方式", "考生号", "联系电话", "电话", "邮箱", "完整档案", "考生名单", "学生名单")
_BULK_MARKERS = (
    "全部学生",
    "所有学生",
    "全部考生",
    "全体考生",
    "学生名单",
    "考生名单",
    "名单发给我",
    "名单给我",
    "导出名单",
    "名单导出",
    "批量导出",
    "批量查询",
    "全部考生",
    "全体考生",
    "学生数据",
    "考生数据",
    "外部网盘",
    "上传到",
)
_LIST_DELIVERY_MARKERS = ("学生名单", "考生名单", "名单发给我", "名单给我", "导出名单", "名单导出", "完整档案", "发到我的邮箱", "上传到外部", "上传到网盘")


@dataclass(slots=True)
class PrivacyAssessment:
    allowed: bool
    risk: float
    reasons: list[str]
    response: str | None = None


def assess_request_privacy(
    message: str,
    *,
    intent: str,
    context_values: dict[str, Any] | None = None,
) -> PrivacyAssessment:
    context_values = context_values or {}
    reasons: list[str] = []
    has_private_field = any(field in message for field in _PRIVATE_FIELDS)
    has_bulk_marker = any(marker in message for marker in _BULK_MARKERS)
    has_list_delivery = any(marker in message for marker in _LIST_DELIVERY_MARKERS)
    if has_list_delivery:
        reasons.append("请求要求交付学生名单")
        return PrivacyAssessment(
            allowed=False,
            risk=1.0,
            reasons=reasons,
            response="该请求涉及学生名单交付，违反招生数据使用边界，不能提供。",
        )
    if has_private_field and has_bulk_marker:
        reasons.append("请求同时涉及敏感字段和批量导出")
        return PrivacyAssessment(
            allowed=False,
            risk=1.0,
            reasons=reasons,
            response="该请求涉及敏感个人字段或批量导出，违反招生数据使用边界，不能提供。",
        )
    wants_individual_field = has_private_field and any(
        marker in message for marker in ("给我", "发给我", "导出", "查看", "查询", "某位", "某个", "全部", "所有")
    )
    if wants_individual_field:
        reasons.append("请求要求提供可识别个人或联系方式字段")
        return PrivacyAssessment(
            allowed=False,
            risk=1.0,
            reasons=reasons,
            response="该请求涉及敏感个人字段，违反招生数据使用边界，不能提供。",
        )
    if "学生" in message and any(marker in message for marker in ("上传", "网盘", "邮箱", "外部")):
        reasons.append("请求要求将学生数据外传")
        return PrivacyAssessment(
            allowed=False,
            risk=1.0,
            reasons=reasons,
            response="学生数据不得上传到外部网盘、邮箱或其他外部系统。",
        )
    if intent == "student_lookup" and not bool(context_values.get("can_lookup_students")):
        reasons.append("当前账号不具备单个学生档案查看权限")
        return PrivacyAssessment(
            allowed=False,
            risk=1.0,
            reasons=reasons,
            response="当前账号无权查看单个学生档案。请联系超级管理员。",
        )
    return PrivacyAssessment(allowed=True, risk=0.0, reasons=reasons)


def assess_result_privacy(
    message: str,
    *,
    intent: str,
    tool_results: list[dict[str, Any]],
    min_cohort_size: int = 5,
) -> PrivacyAssessment:
    if intent != "student_statistics":
        return PrivacyAssessment(allowed=True, risk=0.0, reasons=[])
    specific_selection = any(
        marker in message
        for marker in ("姓", "姓名", "同学", "某个学生", "考生号", "手机号", "身份证")
    )
    if not specific_selection:
        return PrivacyAssessment(allowed=True, risk=0.0, reasons=[])
    counts: list[int] = []
    for result in tool_results:
        metrics = result.get("metrics")
        if not isinstance(metrics, dict):
            continue
        for key in ("student_count", "matched"):
            value = metrics.get(key)
            if isinstance(value, (int, float)):
                counts.append(int(value))
    if counts and 0 < min(counts) < min_cohort_size:
        return PrivacyAssessment(
            allowed=False,
            risk=max(0.75, 1.0 - min(counts) / max(1, min_cohort_size)),
            reasons=[f"小样本统计人数低于隐私阈值 {min_cohort_size}"],
            response="该条件对应的人数较少，依据隐私保护策略不展示具体统计值。请扩大统计范围或调整筛选条件。",
        )
    return PrivacyAssessment(allowed=True, risk=0.0, reasons=[])

