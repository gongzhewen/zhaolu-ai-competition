BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_initial

CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS dim;

CREATE SCHEMA IF NOT EXISTS fact;

CREATE SCHEMA IF NOT EXISTS gov;

CREATE SCHEMA IF NOT EXISTS ai;

CREATE SCHEMA IF NOT EXISTS sys;

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

INSERT INTO sys.role (role_code, role_name)
VALUES
    ('SUPER_ADMIN', '��������Ա'),
    ('ADMISSION_DIRECTOR', '����������'),
    ('ADMISSION_STAFF', '����������Ա'),
    ('DATA_ADMIN', '���ݹ���Ա'),
    ('ANALYST', '���ݷ���Ա'),
    ('VIEWER', 'ֻ���û�')
ON CONFLICT (role_code) DO NOTHING;

INSERT INTO sys.permission (permission_code, permission_name, permission_type)
VALUES
    ('dashboard:view', '�鿴����̨', 'MENU'),
    ('admissions:view', '�鿴��������', 'MENU'),
    ('source:view', '�鿴��Դ����', 'MENU'),
    ('data:import', '��������', 'BUTTON'),
    ('data:quality:manage', '����������������', 'BUTTON'),
    ('ai:chat', 'ʹ�� AI ����', 'BUTTON'),
    ('ai:report', '���� AI ����', 'BUTTON'),
    ('forecast:run', '����Ԥ��', 'BUTTON'),
    ('alert:manage', '����Ԥ��', 'BUTTON'),
    ('report:export', '��������', 'BUTTON'),
    ('system:manage', 'ϵͳ����', 'MENU'),
    ('audit:view', '�鿴�����־', 'MENU')
ON CONFLICT (permission_code) DO NOTHING;

INSERT INTO sys.user_account (username, password_hash, display_name, status)
VALUES (
    'admin',
    'pbkdf2_sha256$260000$BePs2xOG46HZlGY593ltKg$NSPK89uUevA6mDDYens10XojmKyF-ZtCtcFXwwnLrP4',
    'ϵͳ����Ա',
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
    ('410000', '����'),
    ('370000', 'ɽ��'),
    ('130000', '�ӱ�'),
    ('510000', '�Ĵ�'),
    ('440000', '�㶫')
ON CONFLICT (province_code) DO NOTHING;

INSERT INTO dim.subject (subject_code, subject_name, subject_type)
VALUES
    ('PHYSICS', '������', 'GAOKAO'),
    ('HISTORY', '��ʷ��', 'GAOKAO'),
    ('COMPREHENSIVE', '�ۺϸĸ�', 'GAOKAO')
ON CONFLICT (subject_code) DO NOTHING;

INSERT INTO dim.batch (year_id, batch_code, batch_name)
SELECT y.id, b.batch_code, b.batch_name
FROM dim.year y
CROSS JOIN (
    VALUES
        ('UNDERGRADUATE', '������'),
        ('SPECIAL', 'ר��ƻ���'),
        ('VOCATIONAL', 'ר����')
) AS b(batch_code, batch_name)
ON CONFLICT (year_id, batch_code) DO NOTHING;

INSERT INTO dim.plan_type (type_code, type_name)
VALUES
    ('GENERAL', '��ͨ�ƻ�'),
    ('NATIONAL_SPECIAL', '����ר��'),
    ('LOCAL_SPECIAL', '�ط�ר��'),
    ('HIGH_LEVEL', '��ˮƽ�ƻ�')
ON CONFLICT (type_code) DO NOTHING;

INSERT INTO dim.channel (channel_code, channel_name, channel_type)
VALUES
    ('OFFICIAL_SITE', 'ѧУ����', 'ONLINE'),
    ('MINI_PROGRAM', '����С����', 'ONLINE'),
    ('PHONE', '�绰��ѯ', 'OFFLINE'),
    ('OFFLINE_EVENT', '������ѯ��', 'OFFLINE'),
    ('REFERRAL', 'ʦ���Ƽ�', 'SOCIAL')
ON CONFLICT (channel_code) DO NOTHING;

INSERT INTO dim.school (school_code, school_name, school_type)
VALUES ('SCHOOL-001', 'ʾ����У', 'UNDERGRADUATE')
ON CONFLICT (school_code) DO NOTHING;

INSERT INTO dim.major (school_id, major_code, major_name, subject_req)
SELECT s.id, m.major_code, m.major_name, m.subject_req
FROM dim.school s
CROSS JOIN (
    VALUES
        ('080901', '�������ѧ�뼼��', '����+��ѧ'),
        ('080902', '��������', '����+��ѧ'),
        ('080910T', '���ݿ�ѧ������ݼ���', '����+��ѧ'),
        ('080717T', '�˹�����', '����+��ѧ'),
        ('080701', '������Ϣ����', '����+��ѧ'),
        ('120203K', '���ѧ', '����'),
        ('030101K', '��ѧ', '����'),
        ('050101', '��������ѧ', '����')
) AS m(major_code, major_name, subject_req)
WHERE s.school_code = 'SCHOOL-001'
ON CONFLICT (school_id, major_code) DO NOTHING;

INSERT INTO gov.metric_definition
(metric_code, metric_name, metric_formula, dimensions, description, version_no)
VALUES
    ('plan_count', '�����ƻ���', 'SUM(fact.plan.plan_count)', '["year","province","batch","subject","major"]', 'ͳ��ָ����Χ�ڵ������ƻ�����', 'v1'),
    ('admitted_count', 'ʵ��¼ȡ��', 'SUM(fact.admission_summary.admitted_count)', '["year","province","batch","subject","major"]', 'ͳ��ʵ��¼ȡ����', 'v1'),
    ('completion_rate', '�ƻ������', 'admitted_count / NULLIF(plan_count, 0)', '["year","province","batch","subject","major"]', 'ʵ��¼ȡ�����Լƻ���', 'v1'),
    ('min_rank_no', '���¼ȡλ��', 'MIN(fact.admission_summary.min_rank_no)', '["year","province","batch","subject","major"]', 'ָ����Χ�����¼ȡλ��', 'v1')
ON CONFLICT (metric_code) DO NOTHING;

INSERT INTO sys.alert_rule (rule_code, rule_name, rule_expression, severity)
VALUES
    ('LOW_COMPLETION_RATE', '�ƻ������ƫ��', 'completion_rate < 0.8', 'HIGH'),
    ('RANK_CHANGE_LARGE', '���λ�β����쳣', 'ABS(rank_change_rate) > 0.2', 'MEDIUM'),
    ('DATA_QUALITY_HIGH', '������������������', 'data_issue.severity = ''HIGH''', 'HIGH')
ON CONFLICT (rule_code) DO NOTHING;

INSERT INTO alembic_version (version_num) VALUES ('0001_initial') RETURNING alembic_version.version_num;

-- Running upgrade 0001_initial -> 0002_import_pipeline

ALTER TABLE gov.etl_job ADD COLUMN file_size BIGINT;

ALTER TABLE gov.etl_job ADD COLUMN file_suffix VARCHAR(16);

ALTER TABLE gov.etl_job ADD COLUMN encoding VARCHAR(32);

ALTER TABLE gov.etl_job ADD COLUMN sheet_name VARCHAR(255);

ALTER TABLE gov.etl_job ADD COLUMN data_type VARCHAR(64);

ALTER TABLE gov.etl_job ADD COLUMN headers JSONB DEFAULT '[]'::jsonb NOT NULL;

ALTER TABLE gov.etl_job ADD COLUMN preview_data JSONB DEFAULT '[]'::jsonb NOT NULL;

ALTER TABLE gov.etl_job ADD COLUMN mapping_data JSONB DEFAULT '{}'::jsonb NOT NULL;

ALTER TABLE gov.etl_job ADD COLUMN mapping_confirmed BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE gov.etl_job ADD COLUMN target_table VARCHAR(255);

ALTER TABLE gov.etl_job ADD COLUMN total_rows INTEGER DEFAULT 0 NOT NULL;

ALTER TABLE gov.etl_job ADD COLUMN valid_rows INTEGER DEFAULT 0 NOT NULL;

ALTER TABLE gov.etl_job ADD COLUMN invalid_rows INTEGER DEFAULT 0 NOT NULL;

ALTER TABLE gov.etl_job ADD COLUMN started_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE gov.etl_job ADD COLUMN finished_at TIMESTAMP WITH TIME ZONE;

CREATE TABLE gov.import_field_mapping (
    id BIGSERIAL NOT NULL, 
    job_id BIGINT NOT NULL, 
    source_field VARCHAR(255) NOT NULL, 
    target_field VARCHAR(128), 
    confidence FLOAT, 
    confirmed BOOLEAN DEFAULT false NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

CREATE TABLE gov.import_record (
    id BIGSERIAL NOT NULL, 
    job_id BIGINT NOT NULL, 
    row_no INTEGER NOT NULL, 
    raw_data JSONB NOT NULL, 
    normalized_data JSONB, 
    status VARCHAR(32) NOT NULL, 
    error_message TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_import_field_mapping_job ON gov.import_field_mapping (job_id);

CREATE INDEX ix_import_record_job_status ON gov.import_record (job_id, status);

CREATE INDEX ix_etl_job_status ON gov.etl_job (job_status, created_at);

UPDATE alembic_version SET version_num='0002_import_pipeline' WHERE alembic_version.version_num = '0001_initial';

-- Running upgrade 0002_import_pipeline -> 0003_dbf_import

CREATE TABLE gov.dbf_import_batch (
    id BIGSERIAL NOT NULL, 
    batch_name VARCHAR(255) NOT NULL, 
    source_file VARCHAR(255), 
    source_sha256 VARCHAR(64), 
    file_size BIGINT, 
    status VARCHAR(32) NOT NULL, 
    total_files INTEGER DEFAULT 0 NOT NULL, 
    total_records INTEGER DEFAULT 0 NOT NULL, 
    encoding VARCHAR(32), 
    metadata JSONB DEFAULT '{}'::jsonb NOT NULL, 
    error_message TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id)
);

CREATE TABLE gov.dbf_import_table (
    id BIGSERIAL NOT NULL, 
    batch_id BIGINT NOT NULL, 
    table_name VARCHAR(128) NOT NULL, 
    file_name VARCHAR(255) NOT NULL, 
    record_count INTEGER DEFAULT 0 NOT NULL, 
    field_count INTEGER DEFAULT 0 NOT NULL, 
    header_length INTEGER, 
    record_length INTEGER, 
    language_driver INTEGER, 
    fields JSONB DEFAULT '[]'::jsonb NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(batch_id) REFERENCES gov.dbf_import_batch (id) ON DELETE CASCADE
);

CREATE TABLE gov.dbf_import_row (
    id BIGSERIAL NOT NULL, 
    batch_id BIGINT NOT NULL, 
    table_id BIGINT NOT NULL, 
    row_no INTEGER NOT NULL, 
    raw_data JSONB NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uk_dbf_import_row_table_row UNIQUE (table_id, row_no), 
    FOREIGN KEY(batch_id) REFERENCES gov.dbf_import_batch (id) ON DELETE CASCADE, 
    FOREIGN KEY(table_id) REFERENCES gov.dbf_import_table (id) ON DELETE CASCADE
);

CREATE INDEX ix_dbf_import_table_batch ON gov.dbf_import_table (batch_id);

CREATE INDEX ix_dbf_import_row_batch_table ON gov.dbf_import_row (batch_id, table_id);

UPDATE alembic_version SET version_num='0003_dbf_import' WHERE alembic_version.version_num = '0002_import_pipeline';

-- Running upgrade 0003_dbf_import -> 0004_dbf_normalized_data

CREATE TABLE dim.region (
    id BIGSERIAL NOT NULL, 
    region_code VARCHAR(32) NOT NULL, 
    region_name VARCHAR(128) NOT NULL, 
    parent_code VARCHAR(32), 
    region_level INTEGER, 
    data_version VARCHAR(64), 
    PRIMARY KEY (id), 
    UNIQUE (region_code)
);

CREATE TABLE fact.candidate_profile (
    id BIGSERIAL NOT NULL, 
    candidate_key VARCHAR(128) NOT NULL, 
    year_no INTEGER NOT NULL, 
    region_code VARCHAR(32), 
    region_name VARCHAR(128), 
    gender_code VARCHAR(8), 
    gender_name VARCHAR(32), 
    ethnicity_code VARCHAR(16), 
    ethnicity_name VARCHAR(64), 
    exam_type_code VARCHAR(16), 
    exam_type_name VARCHAR(64), 
    subject_category_code VARCHAR(16), 
    candidate_type_code VARCHAR(16), 
    foreign_language_code VARCHAR(16), 
    source_school_code VARCHAR(32), 
    source_school_name VARCHAR(255), 
    household_type_code VARCHAR(16), 
    data_version VARCHAR(64) NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX idx_candidate_profile_key ON fact.candidate_profile (candidate_key);

CREATE INDEX idx_candidate_profile_region ON fact.candidate_profile (year_no, region_code);

CREATE TABLE fact.exam_subject_score (
    id BIGSERIAL NOT NULL, 
    candidate_key VARCHAR(128) NOT NULL, 
    year_no INTEGER NOT NULL, 
    exam_number VARCHAR(32), 
    subject_code VARCHAR(16) NOT NULL, 
    subject_name VARCHAR(64), 
    score_type VARCHAR(16), 
    exam_year_month VARCHAR(16), 
    score NUMERIC(8, 2), 
    grade_point NUMERIC(8, 2), 
    data_version VARCHAR(64) NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX idx_exam_subject_score_candidate ON fact.exam_subject_score (candidate_key, subject_code);

CREATE TABLE fact.major_choice (
    id BIGSERIAL NOT NULL, 
    candidate_key VARCHAR(128) NOT NULL, 
    year_no INTEGER NOT NULL, 
    batch_code VARCHAR(16), 
    subject_code VARCHAR(16), 
    plan_type_code VARCHAR(16), 
    group_code VARCHAR(16), 
    choice_order INTEGER, 
    major_code VARCHAR(64), 
    major_name VARCHAR(255), 
    data_version VARCHAR(64) NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX idx_major_choice_candidate ON fact.major_choice (candidate_key, choice_order);

CREATE TABLE fact.candidate_resume (
    id BIGSERIAL NOT NULL, 
    candidate_key VARCHAR(128) NOT NULL, 
    year_no INTEGER NOT NULL, 
    start_date DATE, 
    end_date DATE, 
    school_name VARCHAR(255), 
    role_name VARCHAR(128), 
    award_name VARCHAR(255), 
    data_version VARCHAR(64) NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX idx_candidate_resume_candidate ON fact.candidate_resume (candidate_key, start_date);

CREATE TABLE fact.medical_summary (
    id BIGSERIAL NOT NULL, 
    candidate_key VARCHAR(128) NOT NULL, 
    year_no INTEGER NOT NULL, 
    medical_result_code VARCHAR(16), 
    medical_result_name VARCHAR(64), 
    restricted_major_codes JSONB, 
    data_version VARCHAR(64) NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX idx_medical_summary_candidate ON fact.medical_summary (candidate_key);

UPDATE alembic_version SET version_num='0004_dbf_normalized_data' WHERE alembic_version.version_num = '0003_dbf_import';

-- Running upgrade 0004_dbf_normalized_data -> 0005_student_management

CREATE TABLE fact.student_management (
    id BIGSERIAL NOT NULL, 
    candidate_key VARCHAR(128) NOT NULL, 
    year_no INTEGER NOT NULL, 
    student_status VARCHAR(32) DEFAULT 'NEW' NOT NULL, 
    follow_up_status VARCHAR(32) DEFAULT 'PENDING' NOT NULL, 
    owner_name VARCHAR(128), 
    tags JSONB DEFAULT '[]'::jsonb NOT NULL, 
    notes TEXT, 
    updated_by_user_id BIGINT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uk_student_management_candidate UNIQUE (candidate_key)
);

CREATE INDEX idx_student_management_status ON fact.student_management (student_status, follow_up_status);

CREATE INDEX idx_student_management_owner ON fact.student_management (owner_name);

UPDATE alembic_version SET version_num='0005_student_management' WHERE alembic_version.version_num = '0004_dbf_normalized_data';

-- Running upgrade 0005_student_management -> 0006_plan_management

INSERT INTO sys.permission (permission_code, permission_name, permission_type)
        VALUES ('admissions:plan:manage', '��д��ά�������ƻ�', 'BUTTON')
        ON CONFLICT (permission_code) DO NOTHING;

INSERT INTO sys.role_permission (role_id, permission_id)
        SELECT r.id, p.id
        FROM sys.role r
        CROSS JOIN sys.permission p
        WHERE r.role_code IN ('SUPER_ADMIN', 'ADMISSION_DIRECTOR', 'DATA_ADMIN')
          AND p.permission_code = 'admissions:plan:manage'
        ON CONFLICT DO NOTHING;

UPDATE alembic_version SET version_num='0006_plan_management' WHERE alembic_version.version_num = '0005_student_management';

-- Running upgrade 0006_plan_management -> 0007_authoritative_admissions

CREATE TABLE fact.authoritative_admission_stat (
    id BIGSERIAL NOT NULL, 
    year_no INTEGER NOT NULL, 
    college_name VARCHAR(255), 
    major_name VARCHAR(255) NOT NULL, 
    plan_count INTEGER DEFAULT '0' NOT NULL, 
    regular_admitted_count INTEGER DEFAULT '0' NOT NULL, 
    zhuan_admitted_count INTEGER DEFAULT '0' NOT NULL, 
    total_admitted_count INTEGER DEFAULT '0' NOT NULL, 
    source_file VARCHAR(512) NOT NULL, 
    data_version VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uk_authoritative_admission_major UNIQUE (year_no, major_name, data_version)
);

CREATE INDEX idx_authoritative_admission_year ON fact.authoritative_admission_stat (year_no, major_name);

UPDATE alembic_version SET version_num='0007_authoritative_admissions' WHERE alembic_version.version_num = '0006_plan_management';

-- Running upgrade 0007_authoritative_admissions -> 0008_major_alias

CREATE TABLE dim.major_alias (
    id BIGSERIAL NOT NULL, 
    source_name VARCHAR(255) NOT NULL, 
    source_name_key VARCHAR(255) NOT NULL, 
    province_id BIGINT, 
    canonical_major_id BIGINT NOT NULL, 
    note TEXT, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(province_id) REFERENCES dim.province (id), 
    FOREIGN KEY(canonical_major_id) REFERENCES dim.major (id)
);

CREATE UNIQUE INDEX uk_major_alias_scope
        ON dim.major_alias (source_name_key, COALESCE(province_id, 0));

CREATE INDEX idx_major_alias_canonical ON dim.major_alias (canonical_major_id, is_active);

UPDATE alembic_version SET version_num='0008_major_alias' WHERE alembic_version.version_num = '0007_authoritative_admissions';

-- Running upgrade 0008_major_alias -> 0009_canonicalization

CREATE TABLE gov.canonicalization_event (
    id BIGSERIAL NOT NULL, 
    pipeline VARCHAR(32) NOT NULL, 
    entity_type VARCHAR(32) NOT NULL, 
    source_value VARCHAR(512) NOT NULL, 
    canonical_value VARCHAR(512) NOT NULL, 
    rule_code VARCHAR(64) NOT NULL, 
    scope_key VARCHAR(128) DEFAULT '' NOT NULL, 
    confidence NUMERIC(5, 4) DEFAULT '1.0' NOT NULL, 
    hit_count BIGINT DEFAULT '1' NOT NULL, 
    first_seen_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX uk_canonicalization_event ON gov.canonicalization_event (pipeline, entity_type, source_value, canonical_value, scope_key);

CREATE INDEX idx_canonicalization_event_type ON gov.canonicalization_event (entity_type, last_seen_at);

UPDATE alembic_version SET version_num='0009_canonicalization' WHERE alembic_version.version_num = '0008_major_alias';

-- Running upgrade 0009_canonicalization -> 0010_student_identity

CREATE TABLE fact.student_identity (
    id BIGSERIAL NOT NULL, 
    candidate_key VARCHAR(128) NOT NULL, 
    year_no INTEGER NOT NULL, 
    candidate_no VARCHAR(64) NOT NULL, 
    student_name VARCHAR(128) NOT NULL, 
    id_card VARCHAR(64), 
    phone VARCHAR(32), 
    address TEXT, 
    data_version VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uk_student_identity_candidate_year UNIQUE (candidate_key, year_no)
);

CREATE INDEX idx_student_identity_year ON fact.student_identity (year_no, candidate_no);

UPDATE alembic_version SET version_num='0010_student_identity' WHERE alembic_version.version_num = '0009_canonicalization';

-- Running upgrade 0010_student_identity -> 0011_exam_score

ALTER TABLE fact.admission_record ADD COLUMN exam_score NUMERIC(8, 2);

UPDATE alembic_version SET version_num='0011_exam_score' WHERE alembic_version.version_num = '0010_student_identity';

-- Running upgrade 0011_exam_score -> 0012_ultimate_admin

INSERT INTO sys.role (role_code, role_name)
            VALUES ('ULTIMATE_ADMIN', '�ռ�����Ա��չʾ������')
            ON CONFLICT (role_code)
            DO UPDATE SET role_name = EXCLUDED.role_name;

INSERT INTO sys.user_account (username, password_hash, display_name, status)
            VALUES (
                'ultimate_admin',
                'pbkdf2_sha256$260000$HK7RqZUYl7_XH5-fwsSl8w$hKpS2T2eBEHRoqX1FWUGAo1c9SnFwYTHMEDEyTrd_-8',
                '����չʾ����Ա',
                'ACTIVE'
            )
            ON CONFLICT (username)
            DO UPDATE SET
                password_hash = EXCLUDED.password_hash,
                display_name = EXCLUDED.display_name,
                status = 'ACTIVE';

INSERT INTO sys.user_role (user_id, role_id)
            SELECT u.id, r.id
            FROM sys.user_account u
            CROSS JOIN sys.role r
            WHERE u.username = 'ultimate_admin'
              AND r.role_code = 'ULTIMATE_ADMIN'
            ON CONFLICT DO NOTHING;

INSERT INTO sys.role_permission (role_id, permission_id)
            SELECT r.id, p.id
            FROM sys.role r
            CROSS JOIN sys.permission p
            WHERE r.role_code = 'ULTIMATE_ADMIN'
            ON CONFLICT DO NOTHING;

UPDATE alembic_version SET version_num='0012_ultimate_admin' WHERE alembic_version.version_num = '0011_exam_score';

-- Running upgrade 0012_ultimate_admin -> 0013_agent_intelligence

ALTER TABLE dim.school ADD COLUMN school_short_name VARCHAR(128);

ALTER TABLE dim.school ADD COLUMN status VARCHAR(32) DEFAULT 'ACTIVE' NOT NULL;

ALTER TABLE dim.school ADD COLUMN timezone VARCHAR(64) DEFAULT 'Asia/Shanghai' NOT NULL;

ALTER TABLE dim.school ADD COLUMN settings JSONB DEFAULT '{}'::jsonb NOT NULL;

ALTER TABLE dim.school ADD COLUMN dbf_profile JSONB DEFAULT '{}'::jsonb NOT NULL;

ALTER TABLE dim.school ADD COLUMN knowledge_scope JSONB DEFAULT '{}'::jsonb NOT NULL;

ALTER TABLE dim.school ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL;

ALTER TABLE gov.dbf_import_batch ADD COLUMN school_id BIGINT;

ALTER TABLE gov.dbf_import_batch ADD COLUMN profile_id BIGINT;

ALTER TABLE gov.dbf_import_batch ADD CONSTRAINT fk_dbf_import_batch_school FOREIGN KEY(school_id) REFERENCES dim.school (id);

CREATE TABLE sys.user_school (
    user_id BIGINT NOT NULL, 
    school_id BIGINT NOT NULL, 
    is_default BOOLEAN DEFAULT false NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (user_id, school_id), 
    FOREIGN KEY(user_id) REFERENCES sys.user_account (id) ON DELETE CASCADE, 
    FOREIGN KEY(school_id) REFERENCES dim.school (id) ON DELETE CASCADE
);

CREATE TABLE gov.dbf_interface_profile (
    id BIGSERIAL NOT NULL, 
    school_id BIGINT NOT NULL, 
    profile_code VARCHAR(128) NOT NULL, 
    profile_name VARCHAR(255) NOT NULL, 
    schema_version VARCHAR(64) NOT NULL, 
    table_catalog JSONB DEFAULT '{}'::jsonb NOT NULL, 
    field_semantics JSONB DEFAULT '{}'::jsonb NOT NULL, 
    canonical_mapping JSONB DEFAULT '{}'::jsonb NOT NULL, 
    validation_rules JSONB DEFAULT '{}'::jsonb NOT NULL, 
    checksum VARCHAR(64), 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(school_id) REFERENCES dim.school (id) ON DELETE CASCADE, 
    CONSTRAINT uk_dbf_profile_school_code UNIQUE (school_id, profile_code)
);

ALTER TABLE ai.knowledge_document ADD COLUMN school_id BIGINT;

ALTER TABLE ai.knowledge_document ADD COLUMN tags JSONB DEFAULT '[]'::jsonb NOT NULL;

ALTER TABLE ai.knowledge_document ADD COLUMN checksum VARCHAR(64);

ALTER TABLE ai.knowledge_document ADD COLUMN metadata JSONB DEFAULT '{}'::jsonb NOT NULL;

ALTER TABLE ai.knowledge_document ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL;

ALTER TABLE ai.knowledge_document ADD CONSTRAINT fk_knowledge_document_school FOREIGN KEY(school_id) REFERENCES dim.school (id);

CREATE INDEX idx_knowledge_document_school_status ON ai.knowledge_document (school_id, status);

CREATE TABLE ai.agent_memory (
    id BIGSERIAL NOT NULL, 
    user_id BIGINT, 
    school_id BIGINT, 
    conversation_id BIGINT, 
    memory_type VARCHAR(64) NOT NULL, 
    memory_key VARCHAR(255) NOT NULL, 
    memory_value JSONB DEFAULT '{}'::jsonb NOT NULL, 
    summary TEXT NOT NULL, 
    confidence NUMERIC(5, 4) DEFAULT '0.8' NOT NULL, 
    importance NUMERIC(5, 4) DEFAULT '0.5' NOT NULL, 
    hit_count INTEGER DEFAULT '0' NOT NULL, 
    last_accessed_at TIMESTAMP WITH TIME ZONE, 
    expires_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES sys.user_account (id) ON DELETE SET NULL, 
    FOREIGN KEY(school_id) REFERENCES dim.school (id) ON DELETE CASCADE, 
    FOREIGN KEY(conversation_id) REFERENCES ai.conversation (id) ON DELETE SET NULL, 
    CONSTRAINT uk_agent_memory_scope_key UNIQUE (user_id, school_id, memory_key)
);

CREATE INDEX idx_agent_memory_query ON ai.agent_memory (user_id, school_id, memory_type);

CREATE TABLE ai.response_evaluation (
    id BIGSERIAL NOT NULL, 
    message_id BIGINT, 
    school_id BIGINT, 
    intent VARCHAR(128), 
    template_id BIGINT, 
    tool_names JSONB DEFAULT '[]'::jsonb NOT NULL, 
    self_check JSONB DEFAULT '{}'::jsonb NOT NULL, 
    score NUMERIC(5, 4) NOT NULL, 
    loss NUMERIC(5, 4) NOT NULL, 
    action VARCHAR(64) DEFAULT 'accepted' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(message_id) REFERENCES ai.message (id) ON DELETE CASCADE, 
    FOREIGN KEY(school_id) REFERENCES dim.school (id) ON DELETE SET NULL
);

CREATE INDEX idx_response_evaluation_school_created ON ai.response_evaluation (school_id, created_at);

CREATE TABLE ai.prompt_template (
    id BIGSERIAL NOT NULL, 
    template_code VARCHAR(128) NOT NULL, 
    task_type VARCHAR(64) NOT NULL, 
    school_id BIGINT, 
    template_name VARCHAR(255) NOT NULL, 
    template_text TEXT NOT NULL, 
    strategy_key VARCHAR(64) NOT NULL, 
    weight NUMERIC(8, 4) DEFAULT '1.0' NOT NULL, 
    usage_count INTEGER DEFAULT '0' NOT NULL, 
    success_count INTEGER DEFAULT '0' NOT NULL, 
    version_no VARCHAR(64) DEFAULT 'v1' NOT NULL, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(school_id) REFERENCES dim.school (id) ON DELETE CASCADE, 
    CONSTRAINT uk_prompt_template_scope UNIQUE (school_id, template_code, strategy_key)
);

ALTER TABLE ai.response_evaluation ADD CONSTRAINT fk_response_evaluation_template FOREIGN KEY(template_id) REFERENCES ai.prompt_template (id) ON DELETE SET NULL;

CREATE TABLE ai.optimization_event (
    id BIGSERIAL NOT NULL, 
    school_id BIGINT, 
    template_id BIGINT, 
    signal_type VARCHAR(64) NOT NULL, 
    reward NUMERIC(6, 4) NOT NULL, 
    previous_weight NUMERIC(8, 4) NOT NULL, 
    new_weight NUMERIC(8, 4) NOT NULL, 
    learning_rate NUMERIC(8, 4) NOT NULL, 
    metadata JSONB DEFAULT '{}'::jsonb NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(school_id) REFERENCES dim.school (id) ON DELETE SET NULL
);

INSERT INTO sys.user_school (user_id, school_id, is_default)
            SELECT u.id, s.id, TRUE
            FROM sys.user_account u
            CROSS JOIN LATERAL (SELECT id FROM dim.school ORDER BY id LIMIT 1) s
            WHERE u.username IN ('admin', 'ultimate_admin')
            ON CONFLICT DO NOTHING;

INSERT INTO ai.prompt_template (
                template_code, task_type, school_id, template_name, template_text,
                strategy_key, weight, version_no
            )
            VALUES
                ('decision_v1', 'decision', NULL, '���߽���ģ��',
                 '�ȸ�����ȷ���ۣ����г��ؼ��������ݡ����ա����������ͷֲ�ִ�н��顣�������ֱ������Թ��߽����',
                 'evidence_first', 1.0, 'v1'),
                ('analysis_v1', 'analysis', NULL, '���ݷ���ģ��',
                 '�ȸ������ݷ�Χ���ٷ����ؼ��仯��ԭ���������������顣�������ֱ������Թ��߽����',
                 'evidence_first', 1.0, 'v1'),
                ('lookup_v1', 'lookup', NULL, '��ʵ��ѯģ��',
                 'ֱ�ӻش���ʵ��ע��ɸѡ������������Ⱥ�������Դ���������޷��ɹ���֧�ֵ��жϡ�',
                 'grounded_answer', 1.0, 'v1'),
                ('policy_v1', 'policy', NULL, '�����ʴ�ģ��',
                 '��������֪ʶ��ش𣬸������ۡ����ñ߽����Դ���޷�ȷ��ʱ��ȷҪ����ѯʡ����Ժ��ѧУ�����졣',
                 'citation_first', 1.0, 'v1'),
                ('default_v1', 'default', NULL, 'ͨ�ûش�ģ��',
                 '����ʹ��ȷ�������ݹ��ߣ������ش����ݲ���ʱ˵��ȱʧ����ñ��졣',
                 'grounded_answer', 1.0, 'v1')
            ON CONFLICT DO NOTHING;

UPDATE alembic_version SET version_num='0013_agent_intelligence' WHERE alembic_version.version_num = '0012_ultimate_admin';

-- Running upgrade 0013_agent_intelligence -> 0014_enrollment_status

CREATE TABLE fact.enrollment_status (
    id BIGSERIAL NOT NULL, 
    candidate_key VARCHAR(128) NOT NULL, 
    year_no INTEGER NOT NULL, 
    candidate_no VARCHAR(64), 
    student_name VARCHAR(128), 
    is_enrolled BOOLEAN DEFAULT false NOT NULL, 
    enrolled_at DATE, 
    remark TEXT, 
    source_file VARCHAR(255), 
    data_version VARCHAR(64) NOT NULL, 
    raw_data JSONB DEFAULT '{}'::jsonb NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uk_enrollment_status_candidate_year UNIQUE (candidate_key, year_no)
);

CREATE INDEX idx_enrollment_status_year_enrolled ON fact.enrollment_status (year_no, is_enrolled);

CREATE INDEX idx_enrollment_status_candidate_no ON fact.enrollment_status (candidate_no);

UPDATE alembic_version SET version_num='0014_enrollment_status' WHERE alembic_version.version_num = '0013_agent_intelligence';

-- Running upgrade 0014_enrollment_status -> 0015_remove_ultimate_admin

WITH target AS (
                SELECT id FROM sys.user_account WHERE username = 'ultimate_admin'
            ), conversations AS (
                SELECT id FROM ai.conversation WHERE user_id IN (SELECT id FROM target)
            )
            DELETE FROM ai.feedback
            WHERE user_id IN (SELECT id FROM target)
               OR message_id IN (
                   SELECT id FROM ai.message WHERE conversation_id IN (SELECT id FROM conversations)
               );

WITH target AS (
                SELECT id FROM sys.user_account WHERE username = 'ultimate_admin'
            ), conversations AS (
                SELECT id FROM ai.conversation WHERE user_id IN (SELECT id FROM target)
            )
            DELETE FROM ai.response_evaluation
            WHERE message_id IN (
                SELECT id FROM ai.message WHERE conversation_id IN (SELECT id FROM conversations)
            );

WITH target AS (
                SELECT id FROM sys.user_account WHERE username = 'ultimate_admin'
            ), conversations AS (
                SELECT id FROM ai.conversation WHERE user_id IN (SELECT id FROM target)
            )
            DELETE FROM ai.tool_call WHERE conversation_id IN (SELECT id FROM conversations);

WITH target AS (
                SELECT id FROM sys.user_account WHERE username = 'ultimate_admin'
            ), conversations AS (
                SELECT id FROM ai.conversation WHERE user_id IN (SELECT id FROM target)
            )
            DELETE FROM ai.agent_memory
            WHERE user_id IN (SELECT id FROM target)
               OR conversation_id IN (SELECT id FROM conversations);

DELETE FROM ai.message
            WHERE conversation_id IN (
                SELECT id FROM ai.conversation
                WHERE user_id IN (SELECT id FROM sys.user_account WHERE username = 'ultimate_admin')
            );

DELETE FROM ai.conversation
            WHERE user_id IN (SELECT id FROM sys.user_account WHERE username = 'ultimate_admin');

DELETE FROM sys.user_school
            WHERE user_id IN (SELECT id FROM sys.user_account WHERE username = 'ultimate_admin');

DELETE FROM sys.user_role
            WHERE user_id IN (SELECT id FROM sys.user_account WHERE username = 'ultimate_admin')
               OR role_id IN (SELECT id FROM sys.role WHERE role_code = 'ULTIMATE_ADMIN');

DELETE FROM sys.role_permission
            WHERE role_id IN (SELECT id FROM sys.role WHERE role_code = 'ULTIMATE_ADMIN');

DELETE FROM sys.user_account WHERE username = 'ultimate_admin';

DELETE FROM sys.role WHERE role_code = 'ULTIMATE_ADMIN';

UPDATE alembic_version SET version_num='0015_remove_ultimate_admin' WHERE alembic_version.version_num = '0014_enrollment_status';

-- Running upgrade 0015_remove_ultimate_admin -> 0016_agent_runtime_optimization

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.mv_admissions_rollup AS
SELECT
    y.year_no,
    p.school_id,
    sc.school_name,
    p.province_id,
    pr.province_name,
    p.major_id AS source_major_id,
    m.major_name AS source_major_name,
    COALESCE(rm.id, m.id) AS canonical_major_id,
    COALESCE(rm.major_name, m.major_name) AS canonical_major_name,
    p.subject_id,
    sub.subject_name,
    p.plan_type_id,
    COALESCE(p.plan_type_id, 0) AS plan_type_key,
    COALESCE(pt.type_code, '') AS plan_type_code,
    p.batch_id,
    COALESCE(SUM(p.plan_count), 0)::bigint AS plan_count,
    COALESCE(SUM(s.admitted_count), 0)::bigint AS admitted_count,
    MIN(NULLIF(s.min_score, 0)) AS min_score,
    MAX(NULLIF(s.max_score, 0)) AS max_score,
    MIN(NULLIF(s.min_rank_no, 0)) AS min_rank_no,
    MAX(p.data_version) AS data_version
FROM fact.plan p
JOIN dim.year y ON y.id = p.year_id
JOIN dim.school sc ON sc.id = p.school_id
JOIN dim.province pr ON pr.id = p.province_id
JOIN dim.major m ON m.id = p.major_id
JOIN dim.subject sub ON sub.id = p.subject_id
LEFT JOIN dim.plan_type pt ON pt.id = p.plan_type_id
LEFT JOIN LATERAL (
    SELECT ma.canonical_major_id
    FROM dim.major_alias ma
    WHERE ma.is_active
      AND ma.source_name_key = lower(
          replace(replace(replace(m.major_name, '��', '('), '��', ')'), ' ', '')
      )
      AND (ma.province_id IS NULL OR ma.province_id = p.province_id)
    ORDER BY (ma.province_id IS NOT NULL) DESC, ma.id DESC
    LIMIT 1
) major_alias ON TRUE
LEFT JOIN dim.major rm ON rm.id = major_alias.canonical_major_id
LEFT JOIN fact.admission_summary s ON s.plan_id = p.id
GROUP BY
    y.year_no, p.school_id, sc.school_name, p.province_id, pr.province_name,
    p.major_id, m.major_name, COALESCE(rm.id, m.id),
    COALESCE(rm.major_name, m.major_name), p.subject_id, sub.subject_name,
    p.plan_type_id, COALESCE(p.plan_type_id, 0), COALESCE(pt.type_code, ''), p.batch_id;

CREATE UNIQUE INDEX IF NOT EXISTS uk_mv_admissions_rollup_grain
    ON analytics.mv_admissions_rollup (
        year_no, school_id, province_id, source_major_id, canonical_major_id,
        subject_id, plan_type_key, batch_id
    );

CREATE INDEX IF NOT EXISTS idx_mv_admissions_year_school_province_major
    ON analytics.mv_admissions_rollup (
        year_no, school_id, province_id, canonical_major_id
    );

CREATE INDEX IF NOT EXISTS idx_mv_admissions_year_school_major
    ON analytics.mv_admissions_rollup (year_no, school_id, canonical_major_id);;

CREATE INDEX IF NOT EXISTS idx_plan_school_year_province_major
                ON fact.plan (school_id, year_id, province_id, major_id);
            CREATE INDEX IF NOT EXISTS idx_admission_summary_plan_cover
                ON fact.admission_summary (plan_id)
                INCLUDE (admitted_count, min_score, max_score, min_rank_no);
            CREATE INDEX IF NOT EXISTS idx_admission_record_year_province_enrolled
                ON fact.admission_record (year_id, province_id, is_enrolled);
            CREATE INDEX IF NOT EXISTS idx_admission_record_year_channel_enrolled
                ON fact.admission_record (year_id, channel_id, is_enrolled);
            CREATE INDEX IF NOT EXISTS idx_candidate_profile_year_gender
                ON fact.candidate_profile (year_no, gender_name);
            CREATE INDEX IF NOT EXISTS idx_student_identity_year_name
                ON fact.student_identity (year_no, student_name);
            CREATE INDEX IF NOT EXISTS idx_message_conversation_id_desc
                ON ai.message (conversation_id, id DESC);
            CREATE INDEX IF NOT EXISTS idx_knowledge_document_school_type_status
                ON ai.knowledge_document (school_id, document_type, status);;

UPDATE alembic_version SET version_num='0016_agent_runtime_optimization' WHERE alembic_version.version_num = '0015_remove_ultimate_admin';

COMMIT;

