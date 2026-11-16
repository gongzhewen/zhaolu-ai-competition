
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS dim;
CREATE SCHEMA IF NOT EXISTS fact;
CREATE SCHEMA IF NOT EXISTS gov;
CREATE SCHEMA IF NOT EXISTS ai;
CREATE SCHEMA IF NOT EXISTS sys;
"""

CORE_TABLE_SQL = """
CREATE TABLE dim.school (
    id BIGSERIAL PRIMARY KEY,
    school_code VARCHAR(64) NOT NULL UNIQUE,
    school_name VARCHAR(255) NOT NULL,
    school_type VARCHAR(64),
    province_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE dim.year (
    id BIGSERIAL PRIMARY KEY,
    year_no INTEGER NOT NULL UNIQUE,
    start_date DATE,
    end_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE dim.province (
    id BIGSERIAL PRIMARY KEY,
    province_code VARCHAR(32) NOT NULL UNIQUE,
    province_name VARCHAR(64) NOT NULL
);

CREATE TABLE dim.major (
    id BIGSERIAL PRIMARY KEY,
    school_id BIGINT NOT NULL REFERENCES dim.school(id),
    major_code VARCHAR(64) NOT NULL,
    major_name VARCHAR(255) NOT NULL,
    major_group VARCHAR(128),
    subject_req VARCHAR(255),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (school_id, major_code)
);

CREATE TABLE dim.subject (
    id BIGSERIAL PRIMARY KEY,
    subject_code VARCHAR(32) NOT NULL UNIQUE,
    subject_name VARCHAR(64) NOT NULL,
    subject_type VARCHAR(32)
);

CREATE TABLE dim.batch (
    id BIGSERIAL PRIMARY KEY,
    year_id BIGINT REFERENCES dim.year(id),
    batch_code VARCHAR(64) NOT NULL,
    batch_name VARCHAR(128) NOT NULL,
    UNIQUE (year_id, batch_code)
);

CREATE TABLE dim.plan_type (
    id BIGSERIAL PRIMARY KEY,
    type_code VARCHAR(64) NOT NULL UNIQUE,
    type_name VARCHAR(128) NOT NULL
);

CREATE TABLE dim.channel (
    id BIGSERIAL PRIMARY KEY,
    channel_code VARCHAR(64) NOT NULL UNIQUE,
    channel_name VARCHAR(128) NOT NULL,
    channel_type VARCHAR(64)
);

CREATE TABLE dim.policy (
    id BIGSERIAL PRIMARY KEY,
    year_id BIGINT REFERENCES dim.year(id),
    province_id BIGINT REFERENCES dim.province(id),
    title VARCHAR(255) NOT NULL,
    doc_no VARCHAR(128),
    effective_date DATE,
    version_no VARCHAR(64) NOT NULL,
    file_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE fact.plan (
    id BIGSERIAL PRIMARY KEY,
    school_id BIGINT NOT NULL REFERENCES dim.school(id),
    year_id BIGINT NOT NULL REFERENCES dim.year(id),
    province_id BIGINT NOT NULL REFERENCES dim.province(id),
    batch_id BIGINT NOT NULL REFERENCES dim.batch(id),
    subject_id BIGINT NOT NULL REFERENCES dim.subject(id),
    major_id BIGINT NOT NULL REFERENCES dim.major(id),
    plan_type_id BIGINT REFERENCES dim.plan_type(id),
    plan_count INTEGER NOT NULL CHECK (plan_count >= 0),
    tuition NUMERIC(12,2),
    policy_id BIGINT REFERENCES dim.policy(id),
    data_version VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE fact.admission_summary (
    id BIGSERIAL PRIMARY KEY,
    plan_id BIGINT REFERENCES fact.plan(id),
    admitted_count INTEGER NOT NULL DEFAULT 0,
    min_score NUMERIC(6,2),
    avg_score NUMERIC(6,2),
    max_score NUMERIC(6,2),
    min_rank_no INTEGER,
    first_choice_count INTEGER DEFAULT 0,
    adjusted_count INTEGER DEFAULT 0,
    data_version VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE fact.admission_record (
    id BIGSERIAL PRIMARY KEY,
    candidate_key VARCHAR(128) NOT NULL,
    year_id BIGINT NOT NULL REFERENCES dim.year(id),
    province_id BIGINT NOT NULL REFERENCES dim.province(id),
    batch_id BIGINT REFERENCES dim.batch(id),
    subject_id BIGINT REFERENCES dim.subject(id),
    major_id BIGINT REFERENCES dim.major(id),
    channel_id BIGINT REFERENCES dim.channel(id),
    score NUMERIC(6,2),
    rank_no INTEGER,
    volunteer_order INTEGER,
    admit_type VARCHAR(64),
    is_enrolled BOOLEAN,
    data_version VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE fact.score_line (
    id BIGSERIAL PRIMARY KEY,
    year_id BIGINT NOT NULL REFERENCES dim.year(id),
    province_id BIGINT NOT NULL REFERENCES dim.province(id),
    batch_id BIGINT REFERENCES dim.batch(id),
    subject_id BIGINT REFERENCES dim.subject(id),
    major_id BIGINT REFERENCES dim.major(id),
    min_score NUMERIC(6,2),
    min_rank_no INTEGER,
    source_type VARCHAR(64),
    data_version VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE fact.consultation (
    id BIGSERIAL PRIMARY KEY,
    year_id BIGINT NOT NULL REFERENCES dim.year(id),
    province_id BIGINT REFERENCES dim.province(id),
    channel_id BIGINT REFERENCES dim.channel(id),
    consultation_type VARCHAR(64),
    status VARCHAR(32),
    contacted_at TIMESTAMPTZ,
    converted BOOLEAN,
    data_version VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE fact.channel_touch (
    id BIGSERIAL PRIMARY KEY,
    year_id BIGINT NOT NULL REFERENCES dim.year(id),
    province_id BIGINT REFERENCES dim.province(id),
    channel_id BIGINT REFERENCES dim.channel(id),
    touch_type VARCHAR(64),
    touch_count INTEGER DEFAULT 0,
    cost_amount NUMERIC(14,2),
    data_version VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE fact.source_quality (
    id BIGSERIAL PRIMARY KEY,
    year_id BIGINT NOT NULL REFERENCES dim.year(id),
    province_id BIGINT NOT NULL REFERENCES dim.province(id),
    major_id BIGINT REFERENCES dim.major(id),
    quality_level VARCHAR(32),
    candidate_count INTEGER DEFAULT 0,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    data_version VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE fact.metric_snapshot (
    id BIGSERIAL PRIMARY KEY,
    year_id BIGINT NOT NULL REFERENCES dim.year(id),
    metric_code VARCHAR(128) NOT NULL,
    dimensions JSONB NOT NULL DEFAULT '{}'::jsonb,
    metric_value NUMERIC(18,4),
    data_version VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE gov.data_source (
    id BIGSERIAL PRIMARY KEY,
    source_name VARCHAR(255) NOT NULL,
    source_type VARCHAR(64),
    connection_config JSONB,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE gov.etl_job (
    id BIGSERIAL PRIMARY KEY,
    source_name VARCHAR(255) NOT NULL,
    job_name VARCHAR(255) NOT NULL,
    job_status VARCHAR(32) NOT NULL,
    file_name VARCHAR(255),
    file_path TEXT,
    year_no INTEGER,
    data_version VARCHAR(64),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE gov.quality_rule (
    id BIGSERIAL PRIMARY KEY,
    rule_code VARCHAR(128) NOT NULL UNIQUE,
    target_table VARCHAR(255) NOT NULL,
    target_field VARCHAR(255),
    rule_type VARCHAR(64) NOT NULL,
    rule_expression TEXT,
    severity VARCHAR(32) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE gov.data_issue (
    id BIGSERIAL PRIMARY KEY,
    rule_id BIGINT REFERENCES gov.quality_rule(id),
    target_table VARCHAR(255),
    record_key VARCHAR(255),
    issue_type VARCHAR(64),
    issue_message TEXT,
    issue_status VARCHAR(32) DEFAULT 'OPEN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE gov.metric_definition (
    id BIGSERIAL PRIMARY KEY,
    metric_code VARCHAR(128) NOT NULL UNIQUE,
    metric_name VARCHAR(255) NOT NULL,
    metric_formula TEXT NOT NULL,
    dimensions JSONB DEFAULT '[]'::jsonb,
    description TEXT,
    version_no VARCHAR(64) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE ai.knowledge_document (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    document_type VARCHAR(64),
    year_id BIGINT REFERENCES dim.year(id),
    province_id BIGINT REFERENCES dim.province(id),
    source_url TEXT,
    version_no VARCHAR(64),
    status VARCHAR(32) DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ai.knowledge_chunk (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES ai.knowledge_document(id),
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    embedding VECTOR(1024),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ai.conversation (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT,
    title VARCHAR(255),
    mode VARCHAR(32) DEFAULT 'AUTO',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ai.message (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL REFERENCES ai.conversation(id),
    role VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    intent VARCHAR(64),
    citations JSONB DEFAULT '[]'::jsonb,
    tool_result JSONB,
    confidence VARCHAR(32),
    token_usage JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ai.tool_call (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT REFERENCES ai.conversation(id),
    tool_name VARCHAR(128) NOT NULL,
    input_params JSONB NOT NULL,
    output_summary JSONB,
    status VARCHAR(32) NOT NULL,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ai.feedback (
    id BIGSERIAL PRIMARY KEY,
    message_id BIGINT REFERENCES ai.message(id),
    user_id BIGINT,
    rating INTEGER,
    feedback_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ai.eval_case (
    id BIGSERIAL PRIMARY KEY,
    case_code VARCHAR(128) NOT NULL UNIQUE,
    category VARCHAR(64),
    question TEXT NOT NULL,
    expected_intent VARCHAR(64),
    expected_answer TEXT,
    expected_tool VARCHAR(128),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE sys.user_account (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(128) NOT NULL UNIQUE,
    password_hash VARCHAR(512) NOT NULL,
    display_name VARCHAR(128),
    status VARCHAR(32) DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sys.role (
    id BIGSERIAL PRIMARY KEY,
    role_code VARCHAR(64) NOT NULL UNIQUE,
    role_name VARCHAR(128) NOT NULL
);

CREATE TABLE sys.permission (
    id BIGSERIAL PRIMARY KEY,
    permission_code VARCHAR(128) NOT NULL UNIQUE,
    permission_name VARCHAR(128) NOT NULL,
    permission_type VARCHAR(32) NOT NULL
);

CREATE TABLE sys.user_role (
    user_id BIGINT NOT NULL REFERENCES sys.user_account(id),
    role_id BIGINT NOT NULL REFERENCES sys.role(id),
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE sys.role_permission (
    role_id BIGINT NOT NULL REFERENCES sys.role(id),
    permission_id BIGINT NOT NULL REFERENCES sys.permission(id),
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE sys.audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT,
    action_type VARCHAR(64) NOT NULL,
    resource_type VARCHAR(64),
    resource_id VARCHAR(128),
    request_data JSONB,
    result_status VARCHAR(32),
    ip_address VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sys.alert_rule (
    id BIGSERIAL PRIMARY KEY,
    rule_code VARCHAR(128) NOT NULL UNIQUE,
    rule_name VARCHAR(255) NOT NULL,
    rule_expression TEXT NOT NULL,
    severity VARCHAR(32) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE sys.alert_record (
    id BIGSERIAL PRIMARY KEY,
    rule_id BIGINT REFERENCES sys.alert_rule(id),
    alert_title VARCHAR(255) NOT NULL,
    alert_content TEXT,
    alert_level VARCHAR(32),
    status VARCHAR(32) DEFAULT 'OPEN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

INDEX_SQL = """
CREATE INDEX idx_plan_dimensions
ON fact.plan (year_id, school_id, province_id, batch_id, subject_id, major_id);

CREATE UNIQUE INDEX uk_plan_natural
ON fact.plan (
    year_id, school_id, province_id, batch_id,
    subject_id, major_id, plan_type_id, data_version
);

CREATE INDEX idx_admission_summary_plan
ON fact.admission_summary (plan_id, data_version);

CREATE INDEX idx_admission_record_dimensions
ON fact.admission_record (year_id, province_id, major_id, subject_id);

CREATE INDEX idx_score_line_dimensions
ON fact.score_line (year_id, province_id, batch_id, subject_id, major_id);

CREATE INDEX idx_metric_snapshot_lookup
ON fact.metric_snapshot (metric_code, year_id);

CREATE INDEX idx_metric_snapshot_dimensions
ON fact.metric_snapshot USING GIN (dimensions);

CREATE INDEX idx_quality_issue_status
ON gov.data_issue (issue_status, created_at DESC);

CREATE INDEX idx_knowledge_chunk_document
ON ai.knowledge_chunk (document_id, chunk_index);

CREATE INDEX idx_knowledge_chunk_metadata
ON ai.knowledge_chunk USING GIN (metadata);

CREATE INDEX idx_ai_message_conversation
ON ai.message (conversation_id, created_at);

CREATE INDEX idx_audit_log_created
ON sys.audit_log (created_at DESC);

CREATE INDEX idx_audit_log_user
ON sys.audit_log (user_id, created_at DESC);
"""

SEED_SQL = """
INSERT INTO sys.role (role_code, role_name)
VALUES
    ('SUPER_ADMIN', '超级管理员'),
    ('ADMISSION_DIRECTOR', '招生负责人'),
    ('ADMISSION_STAFF', '招生工作人员'),
    ('DATA_ADMIN', '数据管理员'),
    ('ANALYST', '数据分析员'),
    ('VIEWER', '只读用户')
ON CONFLICT (role_code) DO NOTHING;

INSERT INTO sys.permission (permission_code, permission_name, permission_type)
VALUES
    ('dashboard:view', '查看工作台', 'MENU'),
    ('admissions:view', '查看招生数据', 'MENU'),
    ('source:view', '查看生源分析', 'MENU'),
    ('data:import', '导入数据', 'BUTTON'),
    ('data:quality:manage', '处理数据质量问题', 'BUTTON'),
    ('ai:chat', '使用 AI 问数', 'BUTTON'),
    ('ai:report', '生成 AI 报告', 'BUTTON'),
    ('forecast:run', '运行预测', 'BUTTON'),
    ('alert:manage', '处理预警', 'BUTTON'),
    ('report:export', '导出报告', 'BUTTON'),
    ('system:manage', '系统管理', 'MENU'),
    ('audit:view', '查看审计日志', 'MENU')
ON CONFLICT (permission_code) DO NOTHING;

INSERT INTO sys.user_account (username, password_hash, display_name, status)
VALUES (
    'admin',
    'pbkdf2_sha256$260000$BePs2xOG46HZlGY593ltKg$NSPK89uUevA6mDDYens10XojmKyF-ZtCtcFXwwnLrP4',
    '系统管理员',
    'ACTIVE'
)
ON CONFLICT (username) DO NOTHING;

INSERT INTO sys.user_role (user_id, role_id)
SELECT u.id, r.id
FROM sys.user_account u, sys.role r
WHERE u.username = 'admin' AND r.role_code = 'SUPER_ADMIN'
ON CONFLICT DO NOTHING;

INSERT INTO sys.role_permission (role_id, permission_id)
SELECT r.id, p.id
FROM sys.role r
CROSS JOIN sys.permission p
WHERE r.role_code = 'SUPER_ADMIN'
ON CONFLICT DO NOTHING;

INSERT INTO dim.year (year_no)
VALUES (2023), (2024), (2025)
ON CONFLICT (year_no) DO NOTHING;

INSERT INTO dim.province (province_code, province_name)
VALUES
    ('410000', '河南'),
    ('370000', '山东'),
    ('130000', '河北'),
    ('510000', '四川'),
    ('440000', '广东')
ON CONFLICT (province_code) DO NOTHING;

INSERT INTO dim.subject (subject_code, subject_name, subject_type)
VALUES
    ('PHYSICS', '物理类', 'GAOKAO'),
    ('HISTORY', '历史类', 'GAOKAO'),
    ('COMPREHENSIVE', '综合改革', 'GAOKAO')
ON CONFLICT (subject_code) DO NOTHING;

INSERT INTO dim.batch (year_id, batch_code, batch_name)
SELECT y.id, b.batch_code, b.batch_name
FROM dim.year y
CROSS JOIN (
    VALUES
        ('UNDERGRADUATE', '本科批'),
        ('SPECIAL', '专项计划批'),
        ('VOCATIONAL', '专科批')
) AS b(batch_code, batch_name)
ON CONFLICT (year_id, batch_code) DO NOTHING;

INSERT INTO dim.plan_type (type_code, type_name)
VALUES
    ('GENERAL', '普通计划'),
    ('NATIONAL_SPECIAL', '国家专项'),
    ('LOCAL_SPECIAL', '地方专项'),
    ('HIGH_LEVEL', '高水平计划')
ON CONFLICT (type_code) DO NOTHING;

INSERT INTO dim.channel (channel_code, channel_name, channel_type)
VALUES
    ('OFFICIAL_SITE', '学校官网', 'ONLINE'),
    ('MINI_PROGRAM', '招生小程序', 'ONLINE'),
    ('PHONE', '电话咨询', 'OFFLINE'),
    ('OFFLINE_EVENT', '线下咨询会', 'OFFLINE'),
    ('REFERRAL', '师生推荐', 'SOCIAL')
ON CONFLICT (channel_code) DO NOTHING;

INSERT INTO dim.school (school_code, school_name, school_type)
VALUES ('SCHOOL-001', '示例高校', 'UNDERGRADUATE')
ON CONFLICT (school_code) DO NOTHING;

INSERT INTO dim.major (school_id, major_code, major_name, subject_req)
SELECT s.id, m.major_code, m.major_name, m.subject_req
FROM dim.school s
CROSS JOIN (
    VALUES
        ('080901', '计算机科学与技术', '物理+化学'),
        ('080902', '软件工程', '物理+化学'),
        ('080910T', '数据科学与大数据技术', '物理+化学'),
        ('080717T', '人工智能', '物理+化学'),
        ('080701', '电子信息工程', '物理+化学'),
        ('120203K', '会计学', '不限'),
        ('030101K', '法学', '不限'),
        ('050101', '汉语言文学', '不限')
) AS m(major_code, major_name, subject_req)
WHERE s.school_code = 'SCHOOL-001'
ON CONFLICT (school_id, major_code) DO NOTHING;

INSERT INTO gov.metric_definition
(metric_code, metric_name, metric_formula, dimensions, description, version_no)
VALUES
    ('plan_count', '招生计划数', 'SUM(fact.plan.plan_count)', '["year","province","batch","subject","major"]', '统计指定范围内的招生计划总数', 'v1'),
    ('admitted_count', '实际录取数', 'SUM(fact.admission_summary.admitted_count)', '["year","province","batch","subject","major"]', '统计实际录取人数', 'v1'),
    ('completion_rate', '计划完成率', 'admitted_count / NULLIF(plan_count, 0)', '["year","province","batch","subject","major"]', '实际录取数除以计划数', 'v1'),
    ('min_rank_no', '最低录取位次', 'MIN(fact.admission_summary.min_rank_no)', '["year","province","batch","subject","major"]', '指定范围内最低录取位次', 'v1')
ON CONFLICT (metric_code) DO NOTHING;

INSERT INTO sys.alert_rule (rule_code, rule_name, rule_expression, severity)
VALUES
    ('LOW_COMPLETION_RATE', '计划完成率偏低', 'completion_rate < 0.8', 'HIGH'),
    ('RANK_CHANGE_LARGE', '最低位次波动异常', 'ABS(rank_change_rate) > 0.2', 'MEDIUM'),
    ('DATA_QUALITY_HIGH', '高严重数据质量问题', 'data_issue.severity = ''HIGH''', 'HIGH')
ON CONFLICT (rule_code) DO NOTHING;
"""


def _execute_sql(block: str) -> None:
    for statement in block.split(";"):
        normalized = statement.strip()
        if normalized:
            op.execute(normalized)


def upgrade() -> None:
    _execute_sql(SCHEMA_SQL)
    _execute_sql(CORE_TABLE_SQL)
    _execute_sql(INDEX_SQL)
    _execute_sql(SEED_SQL)


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS ai CASCADE")
    op.execute("DROP SCHEMA IF EXISTS fact CASCADE")
    op.execute("DROP SCHEMA IF EXISTS gov CASCADE")
    op.execute("DROP SCHEMA IF EXISTS dim CASCADE")
    op.execute("DROP SCHEMA IF EXISTS sys CASCADE")
