from __future__ import annotations
import re

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import rewrite_mysql_schemas
from app.modules.agent.tools.common import bar_chart


METRIC_LABELS = {
    "plan_count": "计划数",
    "admitted_count": "录取数",
    "male_count": "男生数",
    "female_count": "女生数",
    "completion_rate": "计划完成率",
    "enrolled_count": "报到数",
    "enrollment_rate": "报到率",
    "lost_after_admission": "未报到人数",
    "max_score": "最高分",
    "min_score": "最低分",
    "avg_score": "平均分",
    "median_score": "中位分",
    "lower_quartile_score": "下四分位分",
    "min_rank_no": "最高分位次",
    "max_rank_no": "最低分位次",
    "avg_rank_no": "平均分位次",
    "choice_count": "志愿数",
    "choice_rate": "志愿率",
    "applicant_count": "报考数",
    "application_rate": "报考率",
    "first_admitted_count": "一志愿录取数",
    "first_admission_rate": "一志愿录取率",
    "first_applicant_count": "一志愿报考数",
    "first_application_rate": "一志愿报考率",
    "range_admitted_count": "区间志愿录取数",
    "range_admission_rate": "区间志愿录取率",
    "range_applicant_count": "区间志愿报考数",
    "range_application_rate": "区间志愿报考率",
    "adjusted_count": "调剂数",
    "adjusted_rate": "调剂率",
}

DIMENSION_LABELS = {
    "all": "全部",
    "year_no": "年份",
    "province_name": "省份",
    "subject_name": "科类",
    "batch_name": "批次",
    "major_name": "专业",
    "major_group": "学院",
    "level_name": "层次",
    "plan_type": "招生类型",
    "gender_name": "性别",
    "source_school_name": "生源高中",
    "candidate_type_code": "考生类别",
    "foreign_language_code": "外语语种",
    "subject_req": "选科要求",
    "major_code": "专业代码",
}

GROUP_EXPRESSIONS = {
    "year_no": "y.year_no",
    "province_name": "pr.province_name",
    "subject_name": "sub.subject_name",
    "batch_name": "b.batch_name",
    "major_name": "m.major_name",
    "major_group": "COALESCE(NULLIF(m.major_group, ''), '未分组')",
    "level_name": "CASE WHEN pt.type_code='ZHUP' THEN '专升本' ELSE '本科' END",
    "plan_type": "COALESCE(pt.type_name, '未标注')",
    "gender_name": "COALESCE(cp.gender_name, '未标注')",
    "source_school_name": "COALESCE(cp.source_school_name, '未标注')",
    "candidate_type_code": "COALESCE(cp.candidate_type_code, '未标注')",
    "foreign_language_code": "COALESCE(cp.foreign_language_code, '未标注')",
    "subject_req": "COALESCE(NULLIF(m.subject_req, ''), '未设置')",
    "major_code": "m.major_code",
}

METRIC_ALIASES = (
    ("志愿录取情况", ("range_admitted_count", "range_admission_rate")),
    ("志愿报考情况", ("range_applicant_count", "range_application_rate")),
    ("一志愿录取率", ("first_admission_rate", "first_admitted_count")),
    ("一志愿录取数", ("first_admitted_count",)),
    ("一志愿报考率", ("first_application_rate", "first_applicant_count")),
    ("一志愿报考数", ("first_applicant_count",)),
    ("计划完成率", ("completion_rate", "plan_count", "admitted_count")),
    ("报到率", ("enrollment_rate", "enrolled_count", "admitted_count")),
    ("未报到人数", ("lost_after_admission", "enrolled_count", "admitted_count")),
    ("报到人数", ("enrolled_count",)),
    ("报考人数", ("applicant_count",)),
    ("调剂率", ("adjusted_rate", "adjusted_count")),
    ("志愿率", ("choice_rate", "choice_count")),
    ("报考率", ("application_rate", "applicant_count")),
    ("报到数", ("enrolled_count",)),
    ("录取数", ("admitted_count",)),
    ("计划数", ("plan_count",)),
    ("调剂数", ("adjusted_count",)),
    ("志愿数", ("choice_count",)),
    ("志愿总数", ("choice_count",)),
    ("填报专业志愿的考生数", ("applicant_count",)),
    ("报考数", ("applicant_count",)),
    ("男生数", ("male_count",)),
    ("女生数", ("female_count",)),
    ("最高分位次", ("min_rank_no",)),
    ("最低分位次", ("max_rank_no",)),
    ("平均分位次", ("avg_rank_no",)),
    ("最高分", ("max_score",)),
    ("最低分", ("min_score",)),
    ("平均分", ("avg_score",)),
    ("中位分", ("median_score",)),
    ("下四分位分", ("lower_quartile_score",)),
    ("性别情况", ("admitted_count",)),
    ("广东投档排位", ("min_rank_no", "max_rank_no", "avg_rank_no")),
)

UNSUPPORTED_METRICS = (
    "征集数", "专业异动数", "转出专业数", "转入专业数", "计划编制数", "计划调整数",
    "省控线", "最高分线差", "最低分线差", "平均分线差", "位次占比",
)
UNSUPPORTED_DIMENSIONS = (
    "毕业类别", "政治面貌", "年龄", "投档单位代码", "投档单位名称",
    "校区", "地市", "区县", "国际专业代码",
)
BATCH_NAMES = (
    "本科提前批艺术类本科第二批", "艺术第二批(统考本科批)(B段)", "专项南单对口本二",
    "艺术类本科批省考阶段", "体育艺术本一U段", "本科提前批体育类", "艺术体育统考本科批",
    "本科一段 H段", "本科批次B段", "本科批次⑦段", "普通类平行", "本科提前批", "提前录取批",
    "体育类本科批", "艺术类本科批", "艺术本科批", "艺术本科B段", "艺术本科2小批",
    "本科二批", "本科一批", "本科批", "常规批", "专升本", "普通类", "体育本科",
)

CHINESE_ORDERS = {name: index for index, name in enumerate(("一","二","三","四","五","六","七","八","九","十","十一","十二","十三","十四","十五","十六","十七","十八","十九","二十"), 1)}


async def _execute(db: AsyncSession, sql: str, params: dict[str, Any] | None = None):
    return await db.execute(text(rewrite_mysql_schemas(sql)), params or {})

def _parse_top_n(query: str, value: Any = None) -> int:
    if value is not None:
        try:
            return max(1, min(int(value), 50))
        except (TypeError, ValueError):
            pass
    match = re.search(r"前\s*(\d+)", query)
    if match:
        return max(1, min(int(match.group(1)), 50))
    for phrase, number in (("前三", 3), ("前五", 5), ("前十", 10)):
        if phrase in query:
            return number
    return 20


def _parse_sort_ascending(query: str) -> bool | None:
    if any(keyword in query for keyword in ("最低", "最少", "最差", "倒数", "由低到高", "从低到高")):
        return True
    if any(keyword in query for keyword in ("最高", "最多", "最好", "由高到低", "从高到低", "前五", "前三", "前十")):
        return False
    return None


def _detect_metrics(query: str, group_by: str) -> tuple[list[str], list[str], str]:
    scan = query
    metrics: list[str] = []
    for phrase, values in METRIC_ALIASES:
        if phrase in scan:
            for value in values:
                if value not in metrics:
                    metrics.append(value)
            scan = scan.replace(phrase, " ")
    unsupported = [item for item in UNSUPPORTED_METRICS if item in query]
    unsupported.extend(f"维度:{item}" for item in UNSUPPORTED_DIMENSIONS if item in query)
    if "性别情况" in query:
        if group_by == "all":
            group_by = "gender_name"
        else:
            metrics = list(dict.fromkeys([*metrics, "male_count", "female_count"]))
    if "广东投档排位" in query or ("广东" in query and "位次" in query):
        metrics = list(dict.fromkeys([*metrics, "min_rank_no", "max_rank_no", "avg_rank_no"]))
    if "最高分及专业" in query or "最低分及专业" in query:
        group_by = "major_name"
    return metrics, list(dict.fromkeys(unsupported)), group_by


def _detect_group_by(query: str, params_group: str | None) -> str:
    mappings = (
        ("各学院", "major_group"), ("分学院", "major_group"), ("按学院", "major_group"),
        ("专业代码", "major_code"), ("校编代码", "major_code"), ("原始专业代码", "major_code"),
        ("各专业", "major_name"), ("分专业", "major_name"), ("按专业", "major_name"),
        ("各省", "province_name"), ("分省", "province_name"), ("按省份", "province_name"),
        ("各科类", "subject_name"), ("分科类", "subject_name"), ("按科类", "subject_name"),
        ("各批次", "batch_name"), ("分批次", "batch_name"), ("按批次", "batch_name"),
        ("招生类型", "plan_type"), ("层次", "level_name"),
        ("性别情况", "gender_name"), ("按性别", "gender_name"), ("分性别", "gender_name"),
        ("各高中", "source_school_name"), ("按生源高中", "source_school_name"),
        ("考生类别", "candidate_type_code"), ("外语语种", "foreign_language_code"),
        ("选科要求", "subject_req"), ("专业代码", "major_code"),
        ("各年", "year_no"), ("按年份", "year_no"), ("分年份", "year_no"),
    )
    for phrase, field in mappings:
        if phrase in query:
            return field
    if params_group in DIMENSION_LABELS:
        return params_group
    return "all"


def _range_from_query(query: str) -> tuple[int, int]:
    for left, right in CHINESE_ORDERS.items():
        if f"{left}志愿" in query or f"第{left}志愿" in query:
            return CHINESE_ORDERS[left], CHINESE_ORDERS[left]
    for label in ("2~20志愿", "2-20志愿", "2到20志愿", "2至20志愿"):
        if label in query:
            return 2, 20
    return 2, 20


def _filters(params: dict[str, Any], aliases: dict[str, str], include_profile: bool = True, include_plan_type: bool = True) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    binds: dict[str, Any] = {}
    if params.get("school_id") is not None:
        clauses.append(f"{aliases['m']}.school_id=:scope_school_id")
        binds["scope_school_id"] = int(params["school_id"])
    if params.get("year") is not None:
        clauses.append(f"{aliases['y']}.year_no=:year")
        binds["year"] = int(params["year"])
    if params.get("province"):
        clauses.append(f"{aliases['pr']}.province_name=:province")
        binds["province"] = str(params["province"])
    if params.get("major"):
        clauses.append(f"{aliases['m']}.major_name=:major")
        binds["major"] = str(params["major"])
    if params.get("subject_name"):
        clauses.append(f"{aliases['sub']}.subject_name=:subject_name")
        binds["subject_name"] = str(params["subject_name"])
    if params.get("batch_name"):
        clauses.append(f"{aliases['b']}.batch_name=:batch_name")
        binds["batch_name"] = str(params["batch_name"])
    if include_plan_type and params.get("plan_type_code"):
        clauses.append(f"{aliases['pt']}.type_code=:plan_type_code")
        binds["plan_type_code"] = str(params["plan_type_code"])
    if include_profile and params.get("gender_name"):
        clauses.append(f"{aliases['cp']}.gender_name=:gender_name")
        binds["gender_name"] = str(params["gender_name"])
    if include_profile and params.get("source_school_name"):
        clauses.append(f"{aliases['cp']}.source_school_name LIKE :source_school_name")
        binds["source_school_name"] = f"%{params['source_school_name']}%"
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", binds


async def _enrich_params(db: AsyncSession, params: dict[str, Any], query: str) -> dict[str, Any]:
    result = dict(params)
    if not result.get("plan_type_code"):
        if "专升本" in query:
            result["plan_type_code"] = "ZHUP"
        elif "专项" in query:
            result["plan_type_code"] = "SPECIAL"
        elif "普通计划" in query:
            result["plan_type_code"] = "GENERAL"
    if not result.get("batch_name"):
        for batch_name in BATCH_NAMES:
            if batch_name in query:
                result["batch_name"] = batch_name
                break
    return result


def _group_select(group_by: str) -> str:
    return "'全部'" if group_by == "all" else GROUP_EXPRESSIONS[group_by]


async def _plan_rows(db: AsyncSession, group_by: str, params: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if group_by in {"gender_name", "source_school_name", "candidate_type_code", "foreign_language_code"} or params.get("gender_name") or params.get("source_school_name"):
        return {}
    group_expr = _group_select(group_by)
    aliases = {"y":"y","pr":"pr","m":"m","sub":"sub","b":"b","pt":"pt"}
    where_sql, binds = _filters(params, aliases, include_profile=False)
    rows = await _execute(db, f"""
        SELECT {group_expr} AS group_name,
               SUM(p.plan_count) AS plan_count,
               SUM(s.admitted_count) AS plan_admitted_count,
               SUM(s.adjusted_count) AS adjusted_count
        FROM fact.plan p
        JOIN fact.admission_summary s ON s.plan_id=p.id
        JOIN dim.year y ON y.id=p.year_id
        JOIN dim.province pr ON pr.id=p.province_id
        JOIN dim.batch b ON b.id=p.batch_id
        JOIN dim.subject sub ON sub.id=p.subject_id
        JOIN dim.major m ON m.id=p.major_id
        LEFT JOIN dim.plan_type pt ON pt.id=p.plan_type_id
        {where_sql}
        GROUP BY {group_expr}
    """, binds)
    return {str(row["group_name"]): dict(row) for row in rows.mappings().all()}


async def _admission_rows(db: AsyncSession, group_by: str, params: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if group_by in {"major_group", "plan_type"} and group_by not in GROUP_EXPRESSIONS:
        return {}
    group_expr = _group_select(group_by)
    aliases = {"y":"y","pr":"pr","m":"m","sub":"sub","b":"b","pt":"pt","cp":"cp"}
    where_sql, binds = _filters(params, aliases)
    rows = await _execute(db, f"""
        SELECT {group_expr} AS group_name,
               COUNT(*) AS admitted_count,
               SUM(CASE WHEN cp.gender_name='男' THEN 1 ELSE 0 END) AS male_count,
               SUM(CASE WHEN cp.gender_name='女' THEN 1 ELSE 0 END) AS female_count,
               SUM(CASE WHEN ar.is_enrolled=1 THEN 1 ELSE 0 END) AS enrolled_count,
               MAX(ar.score) AS max_score,
               MIN(ar.score) AS min_score,
               ROUND(AVG(ar.score), 2) AS avg_score,
               MIN(ar.rank_no) AS min_rank_no,
               MAX(ar.rank_no) AS max_rank_no,
               ROUND(AVG(ar.rank_no), 2) AS avg_rank_no,
               SUM(CASE WHEN ar.volunteer_order=1 THEN 1 ELSE 0 END) AS first_admitted_count,
               SUM(CASE WHEN ar.volunteer_order BETWEEN :range_min AND :range_max THEN 1 ELSE 0 END) AS range_admitted_count
        FROM fact.admission_record ar
        JOIN dim.year y ON y.id=ar.year_id
        JOIN dim.province pr ON pr.id=ar.province_id
        JOIN dim.batch b ON b.id=ar.batch_id
        JOIN dim.subject sub ON sub.id=ar.subject_id
        JOIN dim.major m ON m.id=ar.major_id
        LEFT JOIN dim.plan_type pt ON pt.type_code=ar.admit_type
        LEFT JOIN fact.candidate_profile cp ON cp.candidate_key=ar.candidate_key AND cp.year_no=y.year_no
        {where_sql}
        GROUP BY {group_expr}
    """, {**binds, "range_min": params["choice_order_min"], "range_max": params["choice_order_max"]})
    return {str(row["group_name"]): dict(row) for row in rows.mappings().all()}


async def _score_quantile_rows(db: AsyncSession, group_by: str, params: dict[str, Any]) -> dict[str, dict[str, Any]]:
    group_expr = _group_select(group_by)
    aliases = {"y":"y","pr":"pr","m":"m","sub":"sub","b":"b","pt":"pt","cp":"cp"}
    where_sql, binds = _filters(params, aliases)
    extra = " AND ar.score IS NOT NULL"
    where_sql = (where_sql + extra) if where_sql else " WHERE ar.score IS NOT NULL"
    rows = await _execute(db, f"""
        WITH scored AS (
            SELECT {group_expr} AS group_name, ar.score,
                   ROW_NUMBER() OVER (PARTITION BY {group_expr} ORDER BY ar.score) AS rn,
                   COUNT(*) OVER (PARTITION BY {group_expr}) AS cnt
            FROM fact.admission_record ar
            JOIN dim.year y ON y.id=ar.year_id
            JOIN dim.province pr ON pr.id=ar.province_id
            JOIN dim.batch b ON b.id=ar.batch_id
            JOIN dim.subject sub ON sub.id=ar.subject_id
            JOIN dim.major m ON m.id=ar.major_id
            LEFT JOIN dim.plan_type pt ON pt.type_code=ar.admit_type
            LEFT JOIN fact.candidate_profile cp ON cp.candidate_key=ar.candidate_key AND cp.year_no=y.year_no
            {where_sql}
        )
        SELECT group_name,
               ROUND(AVG(CASE WHEN rn IN (FLOOR((cnt+1)/2), CEIL((cnt+1)/2)) THEN score END), 2) AS median_score,
               MIN(CASE WHEN rn >= CEIL(cnt*0.25) THEN score END) AS lower_quartile_score
        FROM scored
        GROUP BY group_name
    """, binds)
    return {str(row["group_name"]): dict(row) for row in rows.mappings().all()}


async def _choice_rows(db: AsyncSession, group_by: str, params: dict[str, Any]) -> dict[str, dict[str, Any]]:
    group_expr = _group_select(group_by)
    aliases = {"y":"y","pr":"pr","m":"m","sub":"sub","b":"b","pt":"pt","cp":"cp"}
    where_sql, binds = _filters(params, aliases)
    rows = await _execute(db, f"""
        SELECT {group_expr} AS group_name,
               COUNT(mc.id) AS choice_count,
               COUNT(DISTINCT mc.candidate_key) AS applicant_count,
               COUNT(DISTINCT CASE WHEN mc.choice_order=1 THEN mc.candidate_key END) AS first_applicant_count,
               COUNT(DISTINCT CASE WHEN mc.choice_order BETWEEN :range_min AND :range_max THEN mc.candidate_key END) AS range_applicant_count
        FROM fact.major_choice mc
        JOIN dim.year my ON my.year_no=mc.year_no
        JOIN dim.major m ON m.major_code=mc.major_code
        JOIN fact.admission_record ar ON ar.candidate_key=mc.candidate_key AND ar.year_id=my.id
        JOIN dim.year y ON y.id=ar.year_id
        JOIN dim.province pr ON pr.id=ar.province_id
        JOIN dim.batch b ON b.id=ar.batch_id
        JOIN dim.subject sub ON sub.id=ar.subject_id
        LEFT JOIN dim.plan_type pt ON pt.type_code=ar.admit_type
        LEFT JOIN fact.candidate_profile cp ON cp.candidate_key=ar.candidate_key AND cp.year_no=y.year_no
        {where_sql}
        GROUP BY {group_expr}
    """, {**binds, "range_min": params["choice_order_min"], "range_max": params["choice_order_max"]})
    return {str(row["group_name"]): dict(row) for row in rows.mappings().all()}


def _rate(numerator: Any, denominator: Any) -> float | None:
    try:
        n = float(numerator or 0)
        d = float(denominator or 0)
        return round(n / d * 100, 2) if d else None
    except (TypeError, ValueError):
        return None


def _format(value: Any, metric: str) -> str:
    if value is None or value == "":
        return "-"
    if metric.endswith("_rate"):
        return f"{value}%"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


async def admissions_statistics(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    query = str(params.get("query") or "")
    params = await _enrich_params(db, dict(params), query)
    params["choice_order_min"], params["choice_order_max"] = _range_from_query(query)
    group_by = _detect_group_by(query, params.get("group_by"))
    metrics, unsupported, group_by = _detect_metrics(query, group_by)
    if not metrics and not unsupported:
        metrics = ["admitted_count"]
    supported = [item for item in metrics if item in METRIC_LABELS]
    plan_metrics = {"plan_count", "completion_rate", "adjusted_count", "adjusted_rate"}
    choice_metrics = {
        "choice_count", "choice_rate", "applicant_count", "application_rate",
        "first_applicant_count", "first_application_rate", "range_applicant_count", "range_application_rate",
    }
    admit_metrics = {
        "admitted_count", "male_count", "female_count", "enrolled_count", "enrollment_rate", "lost_after_admission", "max_score", "min_score", "avg_score",
        "median_score", "lower_quartile_score", "min_rank_no", "max_rank_no", "avg_rank_no",
        "first_admitted_count", "first_admission_rate", "range_admitted_count", "range_admission_rate",
    }

    merged: dict[str, dict[str, Any]] = {}
    if any(metric in plan_metrics for metric in supported) or any(
        metric in {"completion_rate", "choice_rate", "application_rate", "first_application_rate", "range_application_rate"}
        for metric in supported
    ):
        for key, row in (await _plan_rows(db, group_by, params)).items():
            merged.setdefault(key, {}).update(row)
    if any(metric in admit_metrics for metric in supported) or any(metric in {"enrollment_rate", "first_admission_rate", "range_admission_rate"} for metric in supported):
        for key, row in (await _admission_rows(db, group_by, params)).items():
            merged.setdefault(key, {}).update(row)
    if any(metric in {"median_score", "lower_quartile_score"} for metric in supported):
        for key, row in (await _score_quantile_rows(db, group_by, params)).items():
            merged.setdefault(key, {}).update(row)
    if any(metric in choice_metrics for metric in supported):
        for key, row in (await _choice_rows(db, group_by, params)).items():
            merged.setdefault(key, {}).update(row)

    for row in merged.values():
        row["completion_rate"] = _rate(row.get("admitted_count"), row.get("plan_count"))
        row["enrollment_rate"] = _rate(row.get("enrolled_count"), row.get("admitted_count"))
        row["lost_after_admission"] = max(int(row.get("admitted_count") or 0) - int(row.get("enrolled_count") or 0), 0)
        row["first_admission_rate"] = _rate(row.get("first_admitted_count"), row.get("admitted_count"))
        row["range_admission_rate"] = _rate(row.get("range_admitted_count"), row.get("admitted_count"))
        row["adjusted_rate"] = _rate(row.get("adjusted_count"), row.get("plan_admitted_count")) if row.get("plan_admitted_count") is not None else _rate(row.get("adjusted_count"), row.get("admitted_count"))
        row["choice_rate"] = _rate(row.get("choice_count"), row.get("plan_count"))
        row["application_rate"] = _rate(row.get("applicant_count"), row.get("plan_count"))
        row["first_application_rate"] = _rate(row.get("first_applicant_count"), row.get("plan_count"))
        row["range_application_rate"] = _rate(row.get("range_applicant_count"), row.get("plan_count"))

    rows = []
    for group_name, values in merged.items():
        row = {**values, "group_name": group_name}
        rows.append(row)
    sort_metric = next((metric for metric in supported if metric in rows[0]), None) if rows else None
    if sort_metric and rows:
        ascending = _parse_sort_ascending(query)
        reverse = (not ascending) if ascending is not None else sort_metric not in {"min_rank_no", "max_rank_no", "avg_rank_no"}
        rows.sort(key=lambda row: (row.get(sort_metric) is None, row.get(sort_metric) if row.get(sort_metric) is not None else 0), reverse=reverse)
    top_n = _parse_top_n(query, params.get("top_n"))
    top_n = max(1, min(top_n, 50))
    rows = rows[:top_n]

    dimension_label = DIMENSION_LABELS.get(group_by, group_by)
    columns = [dimension_label] + [METRIC_LABELS[item] for item in supported if item in METRIC_LABELS]
    table_rows = [[row.get("group_name")] + [row.get(metric) for metric in supported if metric in METRIC_LABELS] for row in rows]

    if unsupported and not supported:
        answer = "当前数据无法可靠计算：" + "、".join(unsupported) + "。这些字段未导入，不能强行生成。"
        return {
            "answer": answer,
            "charts": [],
            "table": None,
            "data_sources": [],
            "metrics": {"unsupported": unsupported, "group_by": group_by},
        }
    if not rows:
        answer = "当前筛选条件下没有找到可用统计数据。"
    else:
        details = "；".join(
            f"{row['group_name']}：" + "、".join(f"{METRIC_LABELS[metric]} {_format(row.get(metric), metric)}" for metric in supported if metric in METRIC_LABELS)
            for row in rows[:10]
        )
        answer = f"按{dimension_label}统计结果：{details}。"
        if unsupported:
            answer += " 当前数据不支持：" + "、".join(unsupported) + "。"
    numeric_metric = next((metric for metric in supported if metric in {"admitted_count", "male_count", "female_count", "plan_count", "max_score", "min_score", "avg_score", "choice_count", "applicant_count"}), None)
    metrics = {
        "group_by": group_by,
        "supported": supported,
        "unsupported": unsupported,
        "row_count": len(rows),
    }
    if len(rows) == 1:
        metrics.update({key: rows[0].get(key) for key in supported})
    chart = bar_chart(
        f"按{dimension_label}统计",
        [str(row["group_name"]) for row in rows[:20]],
        [float(row.get(numeric_metric) or 0) for row in rows[:20]],
    ) if rows and numeric_metric else None
    return {
        "answer": answer,
        "charts": [chart] if chart else [],
        "table": {"columns": columns, "rows": table_rows},
        "data_sources": [
            {"table": "fact.plan", "metric": "计划与调剂"},
            {"table": "fact.admission_record", "metric": "录取、报到、成绩和位次"},
            {"table": "fact.major_choice", "metric": "志愿与报考"},
        ],
        "metrics": metrics,
    }









