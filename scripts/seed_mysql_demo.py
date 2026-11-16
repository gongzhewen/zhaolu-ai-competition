from __future__ import annotations

import asyncio
import json
import os
import random

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.core.text import text
from app.modules.analytics.materialized import refresh_admissions_rollup
from app.modules.rag.service import seed_admissions_knowledge

random.seed(20261002)
DEMO_FORCE_RESET = os.environ.get("DEMO_FORCE_RESET", "0") == "1"

SCHOOL_ID = 1
YEARS = [2022, 2023, 2024, 2025, 2026]
PROVINCES = [
    (1, "430000", "湖南"),
    (2, "420000", "湖北"),
    (3, "440000", "广东"),
    (4, "410000", "河南"),
    (5, "510000", "四川"),
    (6, "370000", "山东"),
]
MAJORS = [
    (1, "080901", "计算机科学与技术", "物理+化学", 1),
    (2, "080902", "软件工程", "物理+化学", 1),
    (3, "080717T", "人工智能", "物理+化学", 1),
    (4, "081001", "土木工程", "物理+化学", 1),
    (5, "120203K", "会计学", "不限", 2),
    (6, "100201K", "临床医学", "物理+化学", 1),
]
CHANNELS = [
    (1, "OFFICIAL_SITE", "学校官网", "ONLINE"),
    (2, "MINI_PROGRAM", "招生小程序", "ONLINE"),
    (3, "PHONE", "电话咨询", "OFFLINE"),
    (4, "OFFLINE_EVENT", "线下咨询会", "OFFLINE"),
]
NAMES = [
    "王小明", "李华", "张伟", "刘洋", "陈晨", "杨帆", "赵敏", "黄鑫",
    "周宁", "吴迪", "徐静", "孙浩", "胡欣", "朱琳", "高远", "林悦",
    "何雨", "郭涛", "马超", "罗佳",
]


async def execute(db, sql: str, params=None):
    return await db.execute(text(sql), params or {})


async def clear_data(db) -> None:
    tables = [
        "ai.optimization_event", "ai.response_evaluation", "ai.prompt_template", "ai.agent_memory",
        "ai.knowledge_chunk", "ai.knowledge_document", "ai.message", "ai.tool_call", "ai.conversation",
        "fact.consultation",
        "fact.exam_subject_score", "fact.major_choice", "fact.medical_summary", "fact.candidate_profile",
        "fact.student_management", "fact.student_identity", "fact.enrollment_status", "fact.admission_record",
        "fact.admission_summary", "fact.plan", "fact.authoritative_admission_stat",
        "dim.school", "dim.major_alias", "dim.channel", "dim.plan_type", "dim.batch", "dim.subject", "dim.major",
        "dim.province", "dim.year", "gov.dbf_interface_profile", "sys.user_role", "sys.role_permission",
        "sys.user_school", "sys.permission", "sys.role", "sys.user_account",
    ]
    await execute(db, "SET FOREIGN_KEY_CHECKS = 0")
    for table in tables:
        await execute(db, f"DELETE FROM {table}")
    await db.commit()
    await execute(db, "SET FOREIGN_KEY_CHECKS = 1")
    await db.commit()


async def seed_dimensions(db) -> None:
    await execute(
        db,
        """
        INSERT INTO dim.school (
            id, school_code, school_name, school_short_name, school_type, province_id,
            status, timezone, settings, dbf_profile, knowledge_scope
        ) VALUES (
            :id, 'SCHOOL-001', '演示大学', '演示大学', 'UNDERGRADUATE', 1,
            'ACTIVE', 'Asia/Shanghai', :settings, :dbf_profile, :knowledge_scope
        )
        """,
        {
            "id": SCHOOL_ID,
            "settings": json.dumps({"demo": True}, ensure_ascii=False),
            "dbf_profile": json.dumps({"schema_version": "dbf-catalog-v1"}, ensure_ascii=False),
            "knowledge_scope": json.dumps({"scope": "school"}, ensure_ascii=False),
        },
    )
    await execute(
        db,
        "INSERT INTO dim.year (id, year_no) VALUES (:id, :year_no)",
        [{"id": index + 1, "year_no": year} for index, year in enumerate(YEARS)],
    )
    await execute(
        db,
        "INSERT INTO dim.province (id, province_code, province_name) VALUES (:id, :code, :name)",
        [{"id": pid, "code": code, "name": name} for pid, code, name in PROVINCES],
    )
    await execute(
        db,
        "INSERT INTO dim.major (id, school_id, major_code, major_name, subject_req, is_active) VALUES (:id, :school_id, :code, :name, :subject_req, TRUE)",
        [
            {"id": mid, "school_id": SCHOOL_ID, "code": code, "name": name, "subject_req": subject_req}
            for mid, code, name, subject_req, _subject_id in MAJORS
        ],
    )
    await execute(
        db,
        "INSERT INTO dim.subject (id, subject_code, subject_name, subject_type) VALUES (:id, :code, :name, 'GAOKAO')",
        [
            {"id": 1, "code": "PHYSICS", "name": "物理类"},
            {"id": 2, "code": "HISTORY", "name": "历史类"},
            {"id": 3, "code": "ZHUP", "name": "专升本"},
        ],
    )
    await execute(
        db,
        "INSERT INTO dim.batch (id, year_id, batch_code, batch_name) VALUES (:id, :year_id, 'UNDERGRADUATE', '本科批')",
        [{"id": index + 1, "year_id": index + 1} for index in range(len(YEARS))],
    )
    await execute(
        db,
        "INSERT INTO dim.plan_type (id, type_code, type_name) VALUES (:id, :code, :name)",
        [
            {"id": 1, "code": "GENERAL", "name": "普通计划"},
            {"id": 2, "code": "ZHUP", "name": "专升本"},
            {"id": 3, "code": "SPECIAL", "name": "专项计划"},
        ],
    )
    await execute(
        db,
        "INSERT INTO dim.channel (id, channel_code, channel_name, channel_type) VALUES (:id, :code, :name, :channel_type)",
        [
            {"id": cid, "code": code, "name": name, "channel_type": channel_type}
            for cid, code, name, channel_type in CHANNELS
        ],
    )
    await execute(
        db,
        "INSERT INTO dim.major_alias (source_name, source_name_key, province_id, canonical_major_id, note, is_active) VALUES (:source, :key, NULL, :major_id, :note, TRUE)",
        [
            {"source": "计科", "key": "计科", "major_id": 1, "note": "通用简称"},
            {"source": "软工", "key": "软工", "major_id": 2, "note": "通用简称"},
            {"source": "土木", "key": "土木", "major_id": 4, "note": "通用简称"},
        ],
    )


async def seed_plans(db) -> None:
    plan_rows = []
    summary_rows = []
    for year_index, year in enumerate(YEARS, start=1):
        for province_id, _code, _name in PROVINCES:
            for major_id, major_code, _major_name, _subject_req, subject_id in MAJORS:
                base = 40 + major_id * 6 + province_id * 2 + year_index * 2
                plan_count = base + (5 if major_id in {1, 2} else 0)
                admitted = max(0, plan_count - (year_index % 3) * 2 - (province_id % 2))
                plan_id = year_index * 1000 + province_id * 100 + major_id
                plan_rows.append(
                    {
                        "id": plan_id,
                        "school_id": SCHOOL_ID,
                        "year_id": year_index,
                        "province_id": province_id,
                        "batch_id": year_index,
                        "subject_id": subject_id,
                        "major_id": major_id,
                        "plan_type_id": 1,
                        "plan_count": plan_count,
                        "tuition": 5200 + major_id * 150,
                        "data_version": f"synthetic-{year}",
                    }
                )
                summary_rows.append(
                    {
                        "plan_id": plan_id,
                        "admitted_count": admitted,
                        "min_score": 500 + major_id * 5 - province_id,
                        "avg_score": 525 + major_id * 5 - province_id,
                        "max_score": 555 + major_id * 6 - province_id,
                        "min_rank_no": 12000 + major_id * 900 + province_id * 300,
                        "first_choice_count": admitted + 10,
                        "adjusted_count": 2 + major_id % 3,
                        "data_version": f"synthetic-{year}",
                    }
                )
    await execute(
        db,
        """
        INSERT INTO fact.plan (
            id, school_id, year_id, province_id, batch_id, subject_id, major_id,
            plan_type_id, plan_count, tuition, data_version
        ) VALUES (
            :id, :school_id, :year_id, :province_id, :batch_id, :subject_id, :major_id,
            :plan_type_id, :plan_count, :tuition, :data_version
        )
        """,
        plan_rows,
    )
    await execute(
        db,
        """
        INSERT INTO fact.admission_summary (
            plan_id, admitted_count, min_score, avg_score, max_score,
            min_rank_no, first_choice_count, adjusted_count, data_version
        ) VALUES (
            :plan_id, :admitted_count, :min_score, :avg_score, :max_score,
            :min_rank_no, :first_choice_count, :adjusted_count, :data_version
        )
        """,
        summary_rows,
    )


async def seed_students(db) -> None:
    records = []
    profiles = []
    identities = []
    management = []
    enrollment = []
    scores = []
    choices = []
    medical = []
    for year_index, year in enumerate(YEARS, start=1):
        for index in range(20):
            candidate_key = f"demo-{year}-{index + 1:03d}"
            candidate_no = f"{year}{index + 1:06d}"
            name = NAMES[index % len(NAMES)]
            province_id = index % len(PROVINCES) + 1
            major_id = index % len(MAJORS) + 1
            subject_id = 1 if major_id <= 4 else 2
            channel_id = index % len(CHANNELS) + 1
            score = 500 + (index * 7 + year_index * 3) % 90
            is_enrolled = index % 5 != 0
            records.append(
                {
                    "candidate_key": candidate_key,
                    "year_id": year_index,
                    "province_id": province_id,
                    "batch_id": year_index,
                    "subject_id": subject_id,
                    "major_id": major_id,
                    "channel_id": channel_id,
                    "score": score,
                    "exam_score": score + 5,
                    "rank_no": 12000 + index * 617 + year_index * 101,
                    "volunteer_order": 1,
                    "admit_type": "GENERAL",
                    "is_enrolled": is_enrolled,
                    "data_version": f"synthetic-{year}",
                }
            )
            profiles.append(
                {
                    "candidate_key": candidate_key,
                    "year_no": year,
                    "region_code": f"R{province_id:02d}",
                    "region_name": PROVINCES[province_id - 1][2],
                    "gender_code": "M" if index % 2 == 0 else "F",
                    "gender_name": "男" if index % 2 == 0 else "女",
                    "ethnicity_code": "01",
                    "ethnicity_name": "汉族",
                    "exam_type_code": "GAOKAO",
                    "exam_type_name": "普通高考",
                    "subject_category_code": "PHYSICS" if subject_id == 1 else "HISTORY",
                    "candidate_type_code": "NORMAL",
                    "foreign_language_code": "EN",
                    "source_school_code": f"HS{province_id:02d}",
                    "source_school_name": f"演示中学{province_id}",
                    "household_type_code": "URBAN",
                    "data_version": f"synthetic-{year}",
                }
            )
            identities.append(
                {
                    "candidate_key": candidate_key,
                    "year_no": year,
                    "candidate_no": candidate_no,
                    "student_name": name,
                    "id_card": None,
                    "phone": None,
                    "address": None,
                    "data_version": f"synthetic-{year}",
                }
            )
            management.append(
                {
                    "candidate_key": candidate_key,
                    "year_no": year,
                    "student_status": "ENROLLED" if is_enrolled else "ADMITTED",
                    "follow_up_status": "COMPLETED" if is_enrolled else "PENDING",
                    "owner_name": "招生管理员",
                    "tags": json.dumps(["演示", "已跟进"], ensure_ascii=False),
                    "notes": "合成演示记录",
                    "updated_by_user_id": 1,
                }
            )
            enrollment.append(
                {
                    "candidate_key": candidate_key,
                    "year_no": year,
                    "candidate_no": candidate_no,
                    "student_name": name,
                    "is_enrolled": is_enrolled,
                    "remark": "演示数据",
                    "source_file": "synthetic",
                    "data_version": f"synthetic-{year}",
                    "raw_data": json.dumps({"synthetic": True}, ensure_ascii=False),
                }
            )
            for subject_name, subject_code, score_value in (
                ("语文", "CHINESE", 80 + index % 25),
                ("数学", "MATH", 75 + (index * 2 + year_index) % 35),
                ("外语", "ENGLISH", 85 + index % 20),
                ("政治", "POLITICS", 65 + index % 25),
            ):
                scores.append(
                    {
                        "candidate_key": candidate_key,
                        "year_no": year,
                        "exam_number": candidate_no,
                        "subject_code": subject_code,
                        "subject_name": subject_name,
                        "score_type": "GAOKAO",
                        "exam_year_month": str(year),
                        "score": score_value,
                        "grade_point": None,
                        "data_version": f"synthetic-{year}",
                    }
                )
            for choice_order in (1, 2):
                choice_major_id = major_id if choice_order == 1 else (major_id % 6) + 1
                choice_major = MAJORS[choice_major_id - 1]
                choices.append(
                    {
                        "candidate_key": candidate_key,
                        "year_no": year,
                        "batch_code": "UNDERGRADUATE",
                        "subject_code": "PHYSICS" if subject_id == 1 else "HISTORY",
                        "plan_type_code": "GENERAL",
                        "group_code": f"G{major_id:02d}",
                        "choice_order": choice_order,
                        "major_code": choice_major[1],
                        "major_name": choice_major[2],
                        "data_version": f"synthetic-{year}",
                    }
                )
            medical.append(
                {
                    "candidate_key": candidate_key,
                    "year_no": year,
                    "medical_result_code": "NORMAL" if index % 7 else "RESTRICTED",
                    "medical_result_name": "体检合格" if index % 7 else "部分专业受限",
                    "restricted_major_codes": json.dumps([] if index % 7 else ["081001"], ensure_ascii=False),
                    "data_version": f"synthetic-{year}",
                }
            )

    await execute(
        db,
        """
        INSERT INTO fact.admission_record (
            candidate_key, year_id, province_id, batch_id, subject_id, major_id, channel_id,
            score, exam_score, rank_no, volunteer_order, admit_type, is_enrolled, data_version
        ) VALUES (
            :candidate_key, :year_id, :province_id, :batch_id, :subject_id, :major_id, :channel_id,
            :score, :exam_score, :rank_no, :volunteer_order, :admit_type, :is_enrolled, :data_version
        )
        """,
        records,
    )
    await execute(
        db,
        """
        INSERT INTO fact.candidate_profile (
            candidate_key, year_no, region_code, region_name, gender_code, gender_name,
            ethnicity_code, ethnicity_name, exam_type_code, exam_type_name,
            subject_category_code, candidate_type_code, foreign_language_code,
            source_school_code, source_school_name, household_type_code, data_version
        ) VALUES (
            :candidate_key, :year_no, :region_code, :region_name, :gender_code, :gender_name,
            :ethnicity_code, :ethnicity_name, :exam_type_code, :exam_type_name,
            :subject_category_code, :candidate_type_code, :foreign_language_code,
            :source_school_code, :source_school_name, :household_type_code, :data_version
        )
        """,
        profiles,
    )
    await execute(
        db,
        """
        INSERT INTO fact.student_identity (
            candidate_key, year_no, candidate_no, student_name, id_card, phone, address, data_version
        ) VALUES (
            :candidate_key, :year_no, :candidate_no, :student_name, :id_card, :phone, :address, :data_version
        )
        """,
        identities,
    )
    await execute(
        db,
        """
        INSERT INTO fact.student_management (
            candidate_key, year_no, student_status, follow_up_status, owner_name,
            tags, notes, updated_by_user_id
        ) VALUES (
            :candidate_key, :year_no, :student_status, :follow_up_status, :owner_name,
            :tags, :notes, :updated_by_user_id
        )
        """,
        management,
    )
    await execute(
        db,
        """
        INSERT INTO fact.enrollment_status (
            candidate_key, year_no, candidate_no, student_name, is_enrolled, remark,
            source_file, data_version, raw_data
        ) VALUES (
            :candidate_key, :year_no, :candidate_no, :student_name, :is_enrolled, :remark,
            :source_file, :data_version, :raw_data
        )
        """,
        enrollment,
    )
    await execute(
        db,
        """
        INSERT INTO fact.exam_subject_score (
            candidate_key, year_no, exam_number, subject_code, subject_name, score_type,
            exam_year_month, score, grade_point, data_version
        ) VALUES (
            :candidate_key, :year_no, :exam_number, :subject_code, :subject_name, :score_type,
            :exam_year_month, :score, :grade_point, :data_version
        )
        """,
        scores,
    )
    await execute(
        db,
        """
        INSERT INTO fact.major_choice (
            candidate_key, year_no, batch_code, subject_code, plan_type_code, group_code,
            choice_order, major_code, major_name, data_version
        ) VALUES (
            :candidate_key, :year_no, :batch_code, :subject_code, :plan_type_code, :group_code,
            :choice_order, :major_code, :major_name, :data_version
        )
        """,
        choices,
    )
    await execute(
        db,
        """
        INSERT INTO fact.medical_summary (
            candidate_key, year_no, medical_result_code, medical_result_name,
            restricted_major_codes, data_version
        ) VALUES (
            :candidate_key, :year_no, :medical_result_code, :medical_result_name,
            :restricted_major_codes, :data_version
        )
        """,
        medical,
    )


async def seed_consultations(db) -> None:
    consultation_types = ("电话咨询", "线上咨询", "现场咨询", "专业咨询")
    rows = []
    for year_index, year in enumerate(YEARS, start=1):
        for index in range(20):
            converted = index % 5 != 0
            rows.append(
                {
                    "year_id": year_index,
                    "province_id": index % len(PROVINCES) + 1,
                    "channel_id": index % len(CHANNELS) + 1,
                    "consultation_type": consultation_types[index % len(consultation_types)],
                    "status": "CONVERTED" if converted else "CONTACTED",
                    "contacted_at": f"{year}-06-{index + 1:02d} 09:00:00",
                    "converted": converted,
                    "data_version": f"synthetic-{year}",
                }
            )
    await execute(
        db,
        """
        INSERT INTO fact.consultation (
            year_id, province_id, channel_id, consultation_type, status,
            contacted_at, converted, data_version
        ) VALUES (
            :year_id, :province_id, :channel_id, :consultation_type, :status,
            :contacted_at, :converted, :data_version
        )
        """,
        rows,
    )


async def seed_official_stats(db) -> None:
    rows = []
    for year_index, year in enumerate(YEARS, start=1):
        plan_count = sum(40 + mid * 6 + pid * 2 + year_index * 2 + (5 if mid in {1, 2} else 0) for pid in range(1, 7) for mid in range(1, 7))
        regular = max(0, plan_count - 12)
        rows.append(
            {
                "year_no": year,
                "college_name": "演示大学",
                "major_name": "",
                "plan_count": plan_count,
                "regular_admitted_count": regular,
                "zhuan_admitted_count": 80 if year_index >= 3 else 0,
                "total_admitted_count": regular + (80 if year_index >= 3 else 0),
                "source_file": "synthetic",
                "data_version": f"official-{year}",
            }
        )
    await execute(
        db,
        """
        INSERT INTO fact.authoritative_admission_stat (
            year_no, college_name, major_name, plan_count, regular_admitted_count,
            zhuan_admitted_count, total_admitted_count, source_file, data_version
        ) VALUES (
            :year_no, :college_name, :major_name, :plan_count, :regular_admitted_count,
            :zhuan_admitted_count, :total_admitted_count, :source_file, :data_version
        )
        """,
        rows,
    )


async def seed_ai(db) -> None:
    await seed_admissions_knowledge(db, school_id=SCHOOL_ID)
    templates = [
        ("lookup", "lookup", "事实查询模板", "先给出准确结果，再列出筛选条件和数据来源。"),
        ("analysis", "analysis", "数据分析模板", "先给出关键指标，再解释变化、结构和对策。"),
        ("decision", "decision", "决策模板", "先给明确结论，再列依据、风险和执行建议。"),
        ("policy", "policy", "政策模板", "先给规则结论，再引用知识库依据和适用条件。"),
        ("default", "default", "通用模板", "结论先行，说明数据来源，最后补充限制。"),
    ]
    for code, task_type, name, template_text in templates:
        await execute(
            db,
            """
            INSERT INTO ai.prompt_template (
                template_code, task_type, school_id, template_name, template_text,
                strategy_key, weight, usage_count, success_count, version_no, is_active
            ) VALUES (
                :code, :task_type, NULL, :name, :template_text,
                'balanced', 1.0, 0, 0, 'v1', TRUE
            )
            """,
            {
                "code": code,
                "task_type": task_type,
                "name": name,
                "template_text": template_text,
            },
        )
    await execute(
        db,
        """
        INSERT INTO gov.dbf_interface_profile (
            school_id, profile_code, profile_name, schema_version,
            table_catalog, field_semantics, canonical_mapping,
            validation_rules, checksum, is_active
        ) VALUES (
            :school_id, 'default-dbf-v1', '学校 DBF 标准接口', 'dbf-catalog-v1',
            :catalog, :field_semantics, :canonical_mapping,
            :validation_rules, :checksum, TRUE
        )
        """,
        {
            "school_id": SCHOOL_ID,
            "catalog": "{}",
            "field_semantics": "{}",
            "canonical_mapping": "{}",
            "validation_rules": "{}",
            "checksum": "synthetic",
        },
    )


async def seed_admin(db) -> None:
    await execute(
        db,
        "INSERT INTO sys.user_account (id, username, password_hash, display_name, status) VALUES (1, 'admin', :password_hash, '系统管理员', 'ACTIVE')",
        {"password_hash": hash_password("ChangeMe123!")},
    )
    await execute(
        db,
        "INSERT INTO sys.role (id, role_code, role_name) VALUES (1, 'SUPER_ADMIN', '超级管理员')",
    )
    permissions = [
        (1, "ai:chat", "AI问答", "API"),
        (2, "system:manage", "系统管理", "API"),
        (3, "admissions:plan:manage", "计划管理", "API"),
        (4, "data:quality:manage", "数据质量管理", "API"),
        (5, "data:import", "数据导入", "API"),
        (6, "report:export", "报告导出", "API"),
        (7, "audit:view", "审计查看", "API"),
    ]
    await execute(
        db,
        "INSERT INTO sys.permission (id, permission_code, permission_name, permission_type) VALUES (:id, :code, :name, :permission_type)",
        [
            {"id": pid, "code": code, "name": name, "permission_type": permission_type}
            for pid, code, name, permission_type in permissions
        ],
    )
    await execute(db, "INSERT INTO sys.user_role (user_id, role_id) VALUES (1, 1)")
    await execute(
        db,
        "INSERT INTO sys.role_permission (role_id, permission_id) VALUES (1, :permission_id)",
        [{"permission_id": item[0]} for item in permissions],
    )
    await execute(
        db,
        "INSERT INTO sys.user_school (user_id, school_id, is_default) VALUES (1, :school_id, TRUE)",
        {"school_id": SCHOOL_ID},
    )


async def existing_business_rows(db) -> int:
    result = await db.execute(
        text(
            """
            SELECT
                (SELECT COUNT(*) FROM fact.plan) +
                (SELECT COUNT(*) FROM fact.student_identity) +
                (SELECT COUNT(*) FROM fact.admission_record)
            """
        )
    )
    return int(result.scalar_one() or 0)


async def main() -> None:
    if not DEMO_FORCE_RESET:
        async with AsyncSessionLocal() as db:
            existing = await existing_business_rows(db)
            consultation_count = int(await db.scalar(text("SELECT COUNT(*) FROM fact.consultation")) or 0)
            faq_document_count = int(await db.scalar(
                text("SELECT COUNT(*) FROM ai.knowledge_document WHERE document_type='policy_faq'")
            ) or 0)
            if existing > 0:
                if consultation_count == 0:
                    await seed_consultations(db)
                    await db.commit()
                if faq_document_count == 0:
                    await seed_admissions_knowledge(db, school_id=SCHOOL_ID)
                if consultation_count == 0 or faq_document_count == 0:
                    print(
                        "mysql_demo_seed=backfilled "
                        f"consultations={consultation_count == 0} knowledge={faq_document_count == 0}"
                    )
                else:
                    print(f"mysql_demo_seed=skipped existing_rows={existing}")
                return
    async with AsyncSessionLocal() as db:
        await clear_data(db)
        await seed_dimensions(db)
        await seed_plans(db)
        await seed_students(db)
        await seed_consultations(db)
        await seed_official_stats(db)
        await seed_ai(db)
        await seed_admin(db)
        await db.commit()
    await refresh_admissions_rollup()
    print("mysql_demo_seed=ok")


if __name__ == "__main__":
    asyncio.run(main())
