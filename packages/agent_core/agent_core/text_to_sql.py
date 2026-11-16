from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from .sql_guard import extract_sql, validate_readonly_sql


ALLOWED_TABLES: set[str] = {
    "dim.year",
    "dim.province",
    "dim.major",
    "dim.major_alias",
    "dim.channel",
    "dim.plan_type",
    "dim.subject",
    "fact.plan",
    "fact.admission_summary",
    "fact.admission_record",
    "fact.candidate_profile",
    "fact.enrollment_status",
    "fact.exam_subject_score",
    "fact.major_choice",
    "fact.medical_summary",
    "fact.consultation",
    "fact.authoritative_admission_stat",
    "analytics.mv_admissions_rollup",
    "zhaolu_dim.year",
    "zhaolu_dim.province",
    "zhaolu_dim.major",
    "zhaolu_dim.major_alias",
    "zhaolu_dim.channel",
    "zhaolu_dim.plan_type",
    "zhaolu_dim.subject",
    "zhaolu_fact.plan",
    "zhaolu_fact.admission_summary",
    "zhaolu_fact.admission_record",
    "zhaolu_fact.candidate_profile",
    "zhaolu_fact.enrollment_status",
    "zhaolu_fact.exam_subject_score",
    "zhaolu_fact.major_choice",
    "zhaolu_fact.medical_summary",
    "zhaolu_fact.consultation",
    "zhaolu_fact.authoritative_admission_stat",
    "zhaolu_analytics.mv_admissions_rollup",
}

SCHEMA_PROMPT = """可用表：
- dim.year(year_no)
- dim.province(province_name)
- dim.major(major_name, is_active)
- dim.major_alias(source_name)
- fact.plan(plan_count, year_id, school_id, province_id, major_id)
- fact.admission_summary(plan_id, admitted_count)
- fact.admission_record(candidate_key, year_id, province_id, major_id, is_enrolled, score)
- fact.enrollment_status(year_no, is_enrolled)
- fact.exam_subject_score(year_no, subject_name, score)
- fact.major_choice(year_no, candidate_key, major_name)
- fact.medical_summary(candidate_key)
- fact.consultation(year_id, converted, province_id, channel_id, consultation_type)
- fact.authoritative_admission_stat(year_no, data_version, total_admitted_count)
- analytics.mv_admissions_rollup(year_no, province_name, canonical_major_name, plan_count, admitted_count)

业务口径：
- 计划完成率 = admitted_count / plan_count * 100
- 报到率 = enrolled_count / candidate_count * 100
- 咨询转化率 = converted_count / consultation_count * 100
- 录取后流失 = admitted_count - enrolled_count

强制规则：
- 不得在 FROM 后写列名，例如禁止 `FROM fact.plan(plan_count, year_id)`。
- 年份必须通过 `JOIN dim.year y ON y.id = p.year_id`，条件使用 `y.year_no`。
- 专业必须通过 `JOIN dim.major m ON m.id = p.major_id`。
- 省份必须通过 `JOIN dim.province pr ON pr.id = p.province_id`。
- 输出列别名必须使用用户给定的指标名。
- 只返回一个 SELECT，不返回解释。

示例1：
{"sql":"SELECT COALESCE(SUM(p.plan_count), 0) AS plan_count FROM fact.plan p JOIN dim.year y ON y.id = p.year_id WHERE y.year_no = 2026 LIMIT 1"}

示例2：
{"sql":"SELECT COALESCE(SUM(p.plan_count), 0) AS plan_count, COALESCE(SUM(s.admitted_count), 0) AS admitted_count FROM fact.plan p JOIN dim.year y ON y.id = p.year_id LEFT JOIN fact.admission_summary s ON s.plan_id = p.id WHERE y.year_no = 2025 LIMIT 1"}

示例3：
{"sql":"SELECT COALESCE(SUM(p.plan_count), 0) AS plan_count, COALESCE(SUM(s.admitted_count), 0) AS admitted_count, ROUND(COALESCE(SUM(s.admitted_count), 0) * 100.0 / NULLIF(SUM(p.plan_count), 0), 2) AS completion_rate FROM fact.plan p JOIN dim.year y ON y.id = p.year_id JOIN dim.major m ON m.id = p.major_id LEFT JOIN fact.admission_summary s ON s.plan_id = p.id WHERE y.year_no = 2025 AND m.major_name = '人工智能' LIMIT 1"}

示例4，生源与报到：
{"sql":"SELECT COUNT(DISTINCT ar.candidate_key) AS candidate_count, SUM(CASE WHEN es.is_enrolled = 1 THEN 1 ELSE 0 END) AS enrolled_count, ROUND(SUM(CASE WHEN es.is_enrolled = 1 THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(DISTINCT ar.candidate_key), 0), 2) AS enrollment_rate FROM fact.admission_record ar JOIN dim.year y ON y.id = ar.year_id LEFT JOIN fact.enrollment_status es ON es.candidate_key = ar.candidate_key AND es.year_no = y.year_no WHERE y.year_no = 2026 LIMIT 1"}

示例5，咨询转化：
{"sql":"SELECT COUNT(*) AS consultation_count, SUM(CASE WHEN c.converted = 1 THEN 1 ELSE 0 END) AS converted_count, ROUND(SUM(CASE WHEN c.converted = 1 THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) AS conversion_rate FROM fact.consultation c JOIN dim.year y ON y.id = c.year_id WHERE y.year_no = 2026 LIMIT 1"}

示例6，专业志愿：
{"sql":"SELECT COUNT(*) AS choice_count, COUNT(DISTINCT mc.candidate_key) AS candidate_count FROM fact.major_choice mc WHERE mc.year_no = 2026 LIMIT 1"}

示例7，学科成绩记录：
{"sql":"SELECT COUNT(*) AS record_count FROM fact.exam_subject_score es JOIN fact.admission_record ar ON ar.candidate_key = es.candidate_key JOIN dim.year y ON y.id = ar.year_id WHERE y.year_no = 2026 LIMIT 1"}

示例8，官方统计数据点：
{"sql":"SELECT COUNT(DISTINCT a.year_no) AS data_points FROM fact.authoritative_admission_stat a WHERE a.year_no = 2026 AND a.data_version LIKE 'official-%' LIMIT 1"}

精确字段提醒：
- candidate_profile：candidate_key, year_no, region_name, gender_name, exam_type_name, subject_category_code。禁止使用 ar.gender 或 cp.gender。
- enrollment_status：candidate_key, year_no, is_enrolled。禁止使用 year_id、plan_id。
- medical_summary：candidate_key, year_no, medical_result_name。禁止使用 year_id、plan_id。
- exam_subject_score：candidate_key, year_no, subject_name, score。禁止使用 year_id。
- major_alias：source_name, canonical_major_id, is_active。禁止使用 major_id。
- admission_summary：plan_id, admitted_count。禁止使用 enrolled_count。
- consultation：year_id, converted。禁止使用 converted_count。
- major_choice：candidate_key, year_no, major_name。禁止使用 choice_count。
- authoritative_admission_stat：year_no, data_version, total_admitted_count。禁止使用 year_id。
不存在派生列 enrolled_count、converted_count、choice_count、data_points。

示例9，招生漏斗：
{"sql":"SELECT COALESCE(SUM(p.plan_count), 0) AS plan_count, COALESCE(SUM(s.admitted_count), 0) AS admitted_count, SUM(CASE WHEN es.is_enrolled = 1 THEN 1 ELSE 0 END) AS enrolled_count, GREATEST(COALESCE(SUM(s.admitted_count), 0) - SUM(CASE WHEN es.is_enrolled = 1 THEN 1 ELSE 0 END), 0) AS lost_after_admission FROM fact.plan p JOIN dim.year y ON y.id = p.year_id LEFT JOIN fact.admission_summary s ON s.plan_id = p.id LEFT JOIN fact.admission_record ar ON ar.year_id = p.year_id AND ar.score IS NOT NULL LEFT JOIN fact.enrollment_status es ON es.candidate_key = ar.candidate_key AND es.year_no = y.year_no WHERE y.year_no = 2026 LIMIT 1"}

示例10，考生画像：
{"sql":"SELECT COUNT(DISTINCT cp.candidate_key) AS candidate_count FROM fact.candidate_profile cp WHERE cp.year_no = 2026 LIMIT 1"}

示例11，体检摘要：
{"sql":"SELECT COUNT(DISTINCT ms.candidate_key) AS candidate_count FROM fact.medical_summary ms WHERE ms.year_no = 2026 LIMIT 1"}

示例12，专业别名：
{"sql":"SELECT COUNT(*) AS matched FROM dim.major_alias ma JOIN dim.major m ON m.id = ma.canonical_major_id WHERE ma.is_active = 1 AND (ma.source_name LIKE '%计算机类%' OR m.major_name LIKE '%计算机类%') LIMIT 1"}
"""


class TextToSqlUnavailable(RuntimeError):
    pass


@dataclass(slots=True)
class LocalTextToSqlClient:
    enabled: bool
    base_url: str
    model_name: str
    api_key: str = ""
    timeout_seconds: float = 15.0
    max_rows: int = 200

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.base_url and self.model_name)

    async def generate_sql(
        self,
        question: str,
        expected_metrics: dict,
        *,
        previous_sql: str | None = None,
        previous_error: str | None = None,
    ) -> str:
        if not self.configured:
            raise TextToSqlUnavailable("本地 Text-to-SQL 模型未配置")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        metric_names = ", ".join(expected_metrics.keys())
        payload = {
            "model": self.model_name,
            "stream": False,
            "temperature": 0,
            "max_tokens": 512,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是只读 MySQL 数据分析器。只输出 JSON：{\"sql\":\"SELECT ...\"}。"
                        "禁止写操作、注释、多语句和敏感个人字段。必须显式列出字段并包含 LIMIT。"
                        + SCHEMA_PROMPT
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"问题：{question}\n"
                        f"查询结果必须使用这些列别名：{metric_names or '按问题需要'}。"
                        + (
                            f"\n上一版SQL执行失败，请修正：{previous_sql}\n错误：{previous_error}"
                            if previous_sql and previous_error
                            else ""
                        )
                    ),
                },
            ],
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
        content = str(data["choices"][0]["message"]["content"])
        sql = extract_sql(content)
        return validate_readonly_sql(sql, allowed_tables=ALLOWED_TABLES, max_rows=self.max_rows)
