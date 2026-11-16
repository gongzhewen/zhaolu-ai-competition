from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics import service
from app.modules.agent.tools.common import bar_chart, pie_chart


async def source_overview(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    overview = await service.get_source_overview(db, year=params.get("year"))
    metrics = overview["metrics"]
    answer = (
        f"当前生源 {metrics['candidate_count']} 人，报到 {metrics['enrolled_count']} 人，"
        f"报到率 {metrics['enrollment_rate']}%。"
    )
    chart = pie_chart(
        "渠道生源分布",
        [{"name": row["channel_name"], "value": row["candidate_count"]} for row in overview["by_channel"]],
    )
    table = {
        "columns": ["渠道", "生源人数", "报到人数", "平均分"],
        "rows": [
            [row["channel_name"], row["candidate_count"], row["enrolled_count"], row["avg_score"]]
            for row in overview["by_channel"]
        ],
    }
    return {
        "answer": answer,
        "charts": [chart],
        "table": table,
        "data_sources": [{"table": "fact.admission_record", "metric": "生源与报到"}],
        "metrics": metrics,
    }


async def candidate_profile(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    overview = await service.get_candidate_profile_overview(
        db,
        year=params.get("year"),
        province=params.get("province"),
        major=params.get("major"),
    )
    metrics = {
        **overview["metrics"],
        "by_gender": {row["name"]: row["count"] for row in overview["by_gender"]},
        "by_subject": {row["name"]: row["count"] for row in overview["by_subject"]},
        "by_region": {row["name"]: row["count"] for row in overview["by_region"]},
    }
    scope = f"{params['major']}专业录取考生" if params.get("major") else "当前考生画像"
    answer = f"{scope}覆盖 {metrics['candidate_count']} 名考生。"
    if overview["by_gender"]:
        answer += " 性别分布为：" + "，".join(
            f"{row['name']} {row['count']} 人" for row in overview["by_gender"]
        ) + "。"
    if overview["by_subject"]:
        answer += " 科类分布为：" + "，".join(
            f"{row['name']} {row['count']} 人" for row in overview["by_subject"]
        ) + "。"
    chart = pie_chart(
        "考生性别分布",
        [{"name": row["name"], "value": row["count"]} for row in overview["by_gender"]],
    )
    table = {
        "columns": ["地区", "人数"],
        "rows": [[row["name"], row["count"]] for row in overview["by_region"][:20]],
    }
    return {
        "answer": answer,
        "charts": [chart],
        "table": table,
        "data_sources": [{"table": "fact.candidate_profile", "metric": "考生画像"}],
        "metrics": metrics,
    }


async def subject_scores(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    overview = await service.get_subject_score_overview(
        db,
        year=params.get("year"),
        province=params.get("province"),
        major=params.get("major"),
    )
    subjects = overview["subjects"]
    record_count = sum(int(row["record_count"] or 0) for row in subjects)
    scope = f"{params['major']}专业录取考生的" if params.get("major") else "当前"
    answer = f"{scope}学科成绩共有 {record_count} 条记录。"
    if subjects:
        high = max(subjects, key=lambda row: float(row["avg_score"] or 0))
        low = min(subjects, key=lambda row: float(row["avg_score"] or 0))
        answer += (
            f" 平均分最高的是{high['subject_name']}，平均 {high['avg_score']} 分；"
            f"平均分最低的是{low['subject_name']}，平均 {low['avg_score']} 分。"
        )
    chart = bar_chart(
        "各科平均分",
        [row["subject_name"] for row in subjects],
        [float(row["avg_score"] or 0) for row in subjects],
    )
    table = {
        "columns": ["科目", "记录数", "平均分", "最低分", "最高分"],
        "rows": [
            [row["subject_name"], row["record_count"], row["avg_score"], row["min_score"], row["max_score"]]
            for row in subjects
        ],
    }
    return {
        "answer": answer,
        "charts": [chart],
        "table": table,
        "data_sources": [{"table": "fact.exam_subject_score", "metric": "学科成绩"}],
        "metrics": {"record_count": record_count},
    }


async def major_choices(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    overview = await service.get_major_choice_overview(
        db,
        year=params.get("year"),
        major=params.get("major"),
    )
    metrics = overview["metrics"]
    top = overview["majors"][0] if overview["majors"] else None
    if params.get("major"):
        answer = (
            f"在专业志愿数据中，{params['major']}共出现 {metrics['choice_count']} 次，"
            f"涉及 {metrics['candidate_count']} 名考生。"
        )
    else:
        answer = f"当前共有 {metrics['choice_count']} 条专业志愿，覆盖 {metrics['candidate_count']} 名考生。"
        if top:
            answer += (
                f" 热度最高的专业是{top['major_name']}，共出现 {top['choice_count']} 次，"
                f"涉及 {top['candidate_count']} 名考生。"
            )
    chart = bar_chart(
        "专业志愿热度",
        [row["major_name"] for row in overview["majors"][:20]],
        [row["choice_count"] for row in overview["majors"][:20]],
    )
    table = {
        "columns": ["专业", "志愿次数", "涉及考生"],
        "rows": [
            [row["major_name"], row["choice_count"], row["candidate_count"]]
            for row in overview["majors"][:30]
        ],
    }
    return {
        "answer": answer,
        "charts": [chart],
        "table": table,
        "data_sources": [{"table": "fact.major_choice", "metric": "专业志愿"}],
        "metrics": metrics,
    }


async def medical_summary(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    overview = await service.get_medical_overview(
        db,
        year=params.get("year"),
        province=params.get("province"),
        major=params.get("major"),
    )
    total = sum(int(row["count"] or 0) for row in overview["medical_results"])
    scope = f"{params['major']}专业录取考生的" if params.get("major") else "当前"
    answer = scope + "体检结论汇总为：" + "，".join(
        f"{row['result_name']} {row['count']} 人" for row in overview["medical_results"]
    ) + "。 不展示个人体检测量信息。"
    chart = pie_chart(
        "体检结论分布",
        [{"name": row["result_name"], "value": row["count"]} for row in overview["medical_results"]],
    )
    table = {
        "columns": ["体检结论", "人数"],
        "rows": [[row["result_name"], row["count"]] for row in overview["medical_results"]],
    }
    return {
        "answer": answer,
        "charts": [chart],
        "table": table,
        "data_sources": [{"table": "fact.medical_summary", "metric": "体检结论摘要"}],
        "metrics": {"candidate_count": total},
    }
