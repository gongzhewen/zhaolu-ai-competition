SET NAMES utf8mb4;

DELETE FROM zhaolu_analytics.mv_admissions_rollup;
DELETE FROM zhaolu_fact.admission_summary;
DELETE FROM zhaolu_fact.admission_record;
DELETE FROM zhaolu_fact.plan;
DELETE FROM zhaolu_dim.major_alias;
DELETE FROM zhaolu_dim.major;
DELETE FROM zhaolu_dim.batch;
DELETE FROM zhaolu_dim.plan_type;
DELETE FROM zhaolu_dim.subject;
DELETE FROM zhaolu_dim.province;
DELETE FROM zhaolu_dim.year;
DELETE FROM zhaolu_dim.school;

INSERT INTO zhaolu_dim.school (
    id, school_code, school_name, school_short_name, school_type, province_id,
    status, timezone, settings, dbf_profile, knowledge_scope
) VALUES (
    2, 'SCHOOL-VERIFY-2', '独立数据面验证学校', '验证学校',
    'UNDERGRADUATE', 1, 'ACTIVE', 'Asia/Shanghai',
    JSON_OBJECT('verification', TRUE),
    JSON_OBJECT('schema_version', 'dbf-catalog-v1'),
    JSON_OBJECT('scope', 'school')
);

INSERT INTO zhaolu_dim.year (id, year_no) VALUES (1, 2026);
INSERT INTO zhaolu_dim.province (id, province_code, province_name)
VALUES (1, '430000', '湖南');
INSERT INTO zhaolu_dim.subject (id, subject_code, subject_name, subject_type)
VALUES (1, 'PHYSICS', '物理类', 'CULTURE');
INSERT INTO zhaolu_dim.batch (id, year_id, batch_code, batch_name)
VALUES (1, 1, 'UNDERGRAD', '本科批');
INSERT INTO zhaolu_dim.plan_type (id, type_code, type_name)
VALUES (1, 'REG', '普通类');
INSERT INTO zhaolu_dim.major (
    id, school_id, major_code, major_name, major_group, subject_req, is_active
) VALUES (
    1, 2, 'VERIFY-001', '独立数据面验证专业', '验证学院', '物理+化学', TRUE
);

INSERT INTO zhaolu_fact.plan (
    id, school_id, year_id, province_id, batch_id, subject_id, major_id,
    plan_type_id, plan_count, tuition, data_version
) VALUES (
    1, 2, 1, 1, 1, 1, 1, 1, 12345, 5000, 'verification-school-2'
);

INSERT INTO zhaolu_fact.admission_summary (
    id, plan_id, admitted_count, min_score, avg_score, max_score,
    min_rank_no, first_choice_count, adjusted_count, data_version
) VALUES (
    1, 1, 100, 520, 560, 600, 1000, 80, 5, 'verification-school-2'
);

INSERT INTO zhaolu_fact.admission_record (
    id, candidate_key, year_id, province_id, batch_id, subject_id, major_id,
    channel_id, score, rank_no, volunteer_order, admit_type, is_enrolled,
    data_version, exam_score
) VALUES (
    1, 'school-2-verify-candidate', 1, 1, 1, 1, 1,
    1, 560, 1000, 1, 'REG', TRUE, 'verification-school-2', 560
);
