-- Generated MySQL Lite schema for zhaolu-ai-v2.

SET NAMES utf8mb4;

SET FOREIGN_KEY_CHECKS = 0;

CREATE DATABASE IF NOT EXISTS `zhaolu_sys` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE DATABASE IF NOT EXISTS `zhaolu_dim` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE DATABASE IF NOT EXISTS `zhaolu_fact` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE DATABASE IF NOT EXISTS `zhaolu_gov` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE DATABASE IF NOT EXISTS `zhaolu_ai` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE DATABASE IF NOT EXISTS `zhaolu_analytics` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE alembic_version (

    version_num VARCHAR(32) NOT NULL, 

    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)

);

CREATE DATABASE IF NOT EXISTS `zhaolu_dim` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE DATABASE IF NOT EXISTS `zhaolu_fact` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE DATABASE IF NOT EXISTS `zhaolu_gov` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE DATABASE IF NOT EXISTS `zhaolu_ai` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE DATABASE IF NOT EXISTS `zhaolu_sys` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE zhaolu_dim.school (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    school_code VARCHAR(64) NOT NULL UNIQUE,

    school_name VARCHAR(255) NOT NULL,

    school_type VARCHAR(64),

    province_id BIGINT,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_dim.year (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    year_no INTEGER NOT NULL UNIQUE,

    start_date DATE,

    end_date DATE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_dim.province (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    province_code VARCHAR(32) NOT NULL UNIQUE,

    province_name VARCHAR(64) NOT NULL

);

CREATE TABLE zhaolu_dim.major (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    school_id BIGINT NOT NULL,

    major_code VARCHAR(64) NOT NULL,

    major_name VARCHAR(255) NOT NULL,

    major_group VARCHAR(128),

    subject_req VARCHAR(255),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (school_id, major_code)

);

CREATE TABLE zhaolu_dim.subject (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    subject_code VARCHAR(32) NOT NULL UNIQUE,

    subject_name VARCHAR(64) NOT NULL,

    subject_type VARCHAR(32)

);

CREATE TABLE zhaolu_dim.batch (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    year_id BIGINT,

    batch_code VARCHAR(64) NOT NULL,

    batch_name VARCHAR(128) NOT NULL,

    UNIQUE (year_id, batch_code)

);

CREATE TABLE zhaolu_dim.plan_type (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    type_code VARCHAR(64) NOT NULL UNIQUE,

    type_name VARCHAR(128) NOT NULL

);

CREATE TABLE zhaolu_dim.channel (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    channel_code VARCHAR(64) NOT NULL UNIQUE,

    channel_name VARCHAR(128) NOT NULL,

    channel_type VARCHAR(64)

);

CREATE TABLE zhaolu_dim.policy (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    year_id BIGINT,

    province_id BIGINT,

    title VARCHAR(255) NOT NULL,

    doc_no VARCHAR(128),

    effective_date DATE,

    version_no VARCHAR(64) NOT NULL,

    file_url TEXT,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_fact.plan (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    school_id BIGINT NOT NULL,

    year_id BIGINT NOT NULL,

    province_id BIGINT NOT NULL,

    batch_id BIGINT NOT NULL,

    subject_id BIGINT NOT NULL,

    major_id BIGINT NOT NULL,

    plan_type_id BIGINT,

    plan_count INTEGER NOT NULL CHECK (plan_count >= 0),

    tuition NUMERIC(12,2),

    policy_id BIGINT,

    data_version VARCHAR(64) NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_fact.admission_summary (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    plan_id BIGINT,

    admitted_count INTEGER NOT NULL DEFAULT 0,

    min_score NUMERIC(6,2),

    avg_score NUMERIC(6,2),

    max_score NUMERIC(6,2),

    min_rank_no INTEGER,

    first_choice_count INTEGER DEFAULT 0,

    adjusted_count INTEGER DEFAULT 0,

    data_version VARCHAR(64) NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_fact.admission_record (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    candidate_key VARCHAR(128) NOT NULL,

    year_id BIGINT NOT NULL,

    province_id BIGINT NOT NULL,

    batch_id BIGINT,

    subject_id BIGINT,

    major_id BIGINT,

    channel_id BIGINT,

    score NUMERIC(6,2),

    rank_no INTEGER,

    volunteer_order INTEGER,

    admit_type VARCHAR(64),

    is_enrolled BOOLEAN,

    data_version VARCHAR(64) NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_fact.score_line (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    year_id BIGINT NOT NULL,

    province_id BIGINT NOT NULL,

    batch_id BIGINT,

    subject_id BIGINT,

    major_id BIGINT,

    min_score NUMERIC(6,2),

    min_rank_no INTEGER,

    source_type VARCHAR(64),

    data_version VARCHAR(64) NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_fact.consultation (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    year_id BIGINT NOT NULL,

    province_id BIGINT,

    channel_id BIGINT,

    consultation_type VARCHAR(64),

    status VARCHAR(32),

    contacted_at TIMESTAMP,

    converted BOOLEAN,

    data_version VARCHAR(64),

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_fact.channel_touch (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    year_id BIGINT NOT NULL,

    province_id BIGINT,

    channel_id BIGINT,

    touch_type VARCHAR(64),

    touch_count INTEGER DEFAULT 0,

    cost_amount NUMERIC(14,2),

    data_version VARCHAR(64),

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_fact.source_quality (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    year_id BIGINT NOT NULL,

    province_id BIGINT NOT NULL,

    major_id BIGINT,

    quality_level VARCHAR(32),

    candidate_count INTEGER DEFAULT 0,

    metrics JSON NOT NULL,

    data_version VARCHAR(64),

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_fact.metric_snapshot (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    year_id BIGINT NOT NULL,

    metric_code VARCHAR(128) NOT NULL,

    dimensions JSON NOT NULL,

    metric_value NUMERIC(18,4),

    data_version VARCHAR(64),

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_gov.data_source (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    source_name VARCHAR(255) NOT NULL,

    source_type VARCHAR(64),

    connection_config JSON,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_gov.etl_job (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    source_name VARCHAR(255) NOT NULL,

    job_name VARCHAR(255) NOT NULL,

    job_status VARCHAR(32) NOT NULL,

    file_name VARCHAR(255),

    file_path TEXT,

    year_no INTEGER,

    data_version VARCHAR(64),

    error_message TEXT,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_gov.quality_rule (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    rule_code VARCHAR(128) NOT NULL UNIQUE,

    target_table VARCHAR(255) NOT NULL,

    target_field VARCHAR(255),

    rule_type VARCHAR(64) NOT NULL,

    rule_expression TEXT,

    severity VARCHAR(32) NOT NULL,

    is_active BOOLEAN NOT NULL DEFAULT TRUE

);

CREATE TABLE zhaolu_gov.data_issue (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    rule_id BIGINT,

    target_table VARCHAR(255),

    record_key VARCHAR(255),

    issue_type VARCHAR(64),

    issue_message TEXT,

    issue_status VARCHAR(32) DEFAULT 'OPEN',

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_gov.metric_definition (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    metric_code VARCHAR(128) NOT NULL UNIQUE,

    metric_name VARCHAR(255) NOT NULL,

    metric_formula TEXT NOT NULL,

    dimensions JSON,

    description TEXT,

    version_no VARCHAR(64) NOT NULL,

    is_active BOOLEAN NOT NULL DEFAULT TRUE

);

CREATE TABLE zhaolu_ai.knowledge_document (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    title VARCHAR(255) NOT NULL,

    document_type VARCHAR(64),

    year_id BIGINT,

    province_id BIGINT,

    source_url TEXT,

    version_no VARCHAR(64),

    status VARCHAR(32) DEFAULT 'ACTIVE',

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_ai.knowledge_chunk (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    document_id BIGINT NOT NULL,

    chunk_index INTEGER NOT NULL,

    content TEXT NOT NULL,

    metadata JSON,

    embedding JSON,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_ai.conversation (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    user_id BIGINT,

    title VARCHAR(255),

    mode VARCHAR(32) DEFAULT 'AUTO',

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_ai.message (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    conversation_id BIGINT NOT NULL,

    role VARCHAR(32) NOT NULL,

    content TEXT NOT NULL,

    intent VARCHAR(64),

    citations JSON,

    tool_result JSON,

    confidence VARCHAR(32),

    token_usage JSON,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_ai.tool_call (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    conversation_id BIGINT,

    tool_name VARCHAR(128) NOT NULL,

    input_params JSON NOT NULL,

    output_summary JSON,

    status VARCHAR(32) NOT NULL,

    duration_ms INTEGER,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_ai.feedback (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    message_id BIGINT,

    user_id BIGINT,

    rating INTEGER,

    feedback_text TEXT,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_ai.eval_case (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    case_code VARCHAR(128) NOT NULL UNIQUE,

    category VARCHAR(64),

    question TEXT NOT NULL,

    expected_intent VARCHAR(64),

    expected_answer TEXT,

    expected_tool VARCHAR(128),

    is_active BOOLEAN DEFAULT TRUE

);

CREATE TABLE zhaolu_sys.user_account (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    username VARCHAR(128) NOT NULL UNIQUE,

    password_hash VARCHAR(512) NOT NULL,

    display_name VARCHAR(128),

    status VARCHAR(32) DEFAULT 'ACTIVE',

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_sys.role (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    role_code VARCHAR(64) NOT NULL UNIQUE,

    role_name VARCHAR(128) NOT NULL

);

CREATE TABLE zhaolu_sys.permission (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    permission_code VARCHAR(128) NOT NULL UNIQUE,

    permission_name VARCHAR(128) NOT NULL,

    permission_type VARCHAR(32) NOT NULL

);

CREATE TABLE zhaolu_sys.user_role (

    user_id BIGINT NOT NULL,

    role_id BIGINT NOT NULL,

    PRIMARY KEY (user_id, role_id)

);

CREATE TABLE zhaolu_sys.role_permission (

    role_id BIGINT NOT NULL,

    permission_id BIGINT NOT NULL,

    PRIMARY KEY (role_id, permission_id)

);

CREATE TABLE zhaolu_sys.audit_log (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    user_id BIGINT,

    action_type VARCHAR(64) NOT NULL,

    resource_type VARCHAR(64),

    resource_id VARCHAR(128),

    request_data JSON,

    result_status VARCHAR(32),

    ip_address VARCHAR(64),

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE zhaolu_sys.alert_rule (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    rule_code VARCHAR(128) NOT NULL UNIQUE,

    rule_name VARCHAR(255) NOT NULL,

    rule_expression TEXT NOT NULL,

    severity VARCHAR(32) NOT NULL,

    is_active BOOLEAN DEFAULT TRUE

);

CREATE TABLE zhaolu_sys.alert_record (

    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    rule_id BIGINT,

    alert_title VARCHAR(255) NOT NULL,

    alert_content TEXT,

    alert_level VARCHAR(32),

    status VARCHAR(32) DEFAULT 'OPEN',

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

);

ALTER TABLE zhaolu_gov.etl_job ADD COLUMN file_size BIGINT;

ALTER TABLE zhaolu_gov.etl_job ADD COLUMN file_suffix VARCHAR(16);

ALTER TABLE zhaolu_gov.etl_job ADD COLUMN encoding VARCHAR(32);

ALTER TABLE zhaolu_gov.etl_job ADD COLUMN sheet_name VARCHAR(255);

ALTER TABLE zhaolu_gov.etl_job ADD COLUMN data_type VARCHAR(64);

ALTER TABLE zhaolu_gov.etl_job ADD COLUMN headers JSON NOT NULL;

ALTER TABLE zhaolu_gov.etl_job ADD COLUMN preview_data JSON NOT NULL;

ALTER TABLE zhaolu_gov.etl_job ADD COLUMN mapping_data JSON NOT NULL;

ALTER TABLE zhaolu_gov.etl_job ADD COLUMN mapping_confirmed BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE zhaolu_gov.etl_job ADD COLUMN target_table VARCHAR(255);

ALTER TABLE zhaolu_gov.etl_job ADD COLUMN total_rows INTEGER DEFAULT 0 NOT NULL;

ALTER TABLE zhaolu_gov.etl_job ADD COLUMN valid_rows INTEGER DEFAULT 0 NOT NULL;

ALTER TABLE zhaolu_gov.etl_job ADD COLUMN invalid_rows INTEGER DEFAULT 0 NOT NULL;

ALTER TABLE zhaolu_gov.etl_job ADD COLUMN started_at TIMESTAMP;

ALTER TABLE zhaolu_gov.etl_job ADD COLUMN finished_at TIMESTAMP;

CREATE TABLE zhaolu_gov.import_field_mapping (

    id BIGINT AUTO_INCREMENT NOT NULL, 

    job_id BIGINT NOT NULL, 

    source_field VARCHAR(255) NOT NULL, 

    target_field VARCHAR(128), 

    confidence FLOAT, 

    confirmed BOOLEAN DEFAULT false NOT NULL, 

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    PRIMARY KEY (id)

);

CREATE TABLE zhaolu_gov.import_record (

    id BIGINT AUTO_INCREMENT NOT NULL, 

    job_id BIGINT NOT NULL, 

    row_no INTEGER NOT NULL, 

    raw_data JSON NOT NULL, 

    normalized_data JSON, 

    status VARCHAR(32) NOT NULL, 

    error_message TEXT, 

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    PRIMARY KEY (id)

);

CREATE TABLE zhaolu_gov.dbf_import_batch (

    id BIGINT AUTO_INCREMENT NOT NULL, 

    batch_name VARCHAR(255) NOT NULL, 

    source_file VARCHAR(255), 

    source_sha256 VARCHAR(64), 

    file_size BIGINT, 

    status VARCHAR(32) NOT NULL, 

    total_files INTEGER DEFAULT 0 NOT NULL, 

    total_records INTEGER DEFAULT 0 NOT NULL, 

    encoding VARCHAR(32), 

    metadata JSON NOT NULL, 

    error_message TEXT, 

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    finished_at TIMESTAMP, 

    PRIMARY KEY (id)

);

CREATE TABLE zhaolu_gov.dbf_import_table (

    id BIGINT AUTO_INCREMENT NOT NULL, 

    batch_id BIGINT NOT NULL, 

    table_name VARCHAR(128) NOT NULL, 

    file_name VARCHAR(255) NOT NULL, 

    record_count INTEGER DEFAULT 0 NOT NULL, 

    field_count INTEGER DEFAULT 0 NOT NULL, 

    header_length INTEGER, 

    record_length INTEGER, 

    language_driver INTEGER, 

    fields JSON NOT NULL, 

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    PRIMARY KEY (id)

);

CREATE TABLE zhaolu_gov.dbf_import_row (

    id BIGINT AUTO_INCREMENT NOT NULL, 

    batch_id BIGINT NOT NULL, 

    table_id BIGINT NOT NULL, 

    row_no INTEGER NOT NULL, 

    raw_data JSON NOT NULL, 

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    PRIMARY KEY (id), 

    CONSTRAINT uk_dbf_import_row_table_row UNIQUE (table_id, row_no)

);

CREATE TABLE zhaolu_dim.region (

    id BIGINT AUTO_INCREMENT NOT NULL, 

    region_code VARCHAR(32) NOT NULL, 

    region_name VARCHAR(128) NOT NULL, 

    parent_code VARCHAR(32), 

    region_level INTEGER, 

    data_version VARCHAR(64), 

    PRIMARY KEY (id), 

    UNIQUE (region_code)

);

CREATE TABLE zhaolu_fact.candidate_profile (

    id BIGINT AUTO_INCREMENT NOT NULL, 

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

CREATE TABLE zhaolu_fact.exam_subject_score (

    id BIGINT AUTO_INCREMENT NOT NULL, 

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

CREATE TABLE zhaolu_fact.major_choice (

    id BIGINT AUTO_INCREMENT NOT NULL, 

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

CREATE TABLE zhaolu_fact.candidate_resume (

    id BIGINT AUTO_INCREMENT NOT NULL, 

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

CREATE TABLE zhaolu_fact.medical_summary (

    id BIGINT AUTO_INCREMENT NOT NULL, 

    candidate_key VARCHAR(128) NOT NULL, 

    year_no INTEGER NOT NULL, 

    medical_result_code VARCHAR(16), 

    medical_result_name VARCHAR(64), 

    restricted_major_codes JSON, 

    data_version VARCHAR(64) NOT NULL, 

    PRIMARY KEY (id)

);

CREATE TABLE zhaolu_fact.student_management (

    id BIGINT AUTO_INCREMENT NOT NULL, 

    candidate_key VARCHAR(128) NOT NULL, 

    year_no INTEGER NOT NULL, 

    student_status VARCHAR(32) DEFAULT 'NEW' NOT NULL, 

    follow_up_status VARCHAR(32) DEFAULT 'PENDING' NOT NULL, 

    owner_name VARCHAR(128), 

    tags JSON NOT NULL, 

    notes TEXT, 

    updated_by_user_id BIGINT, 

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    PRIMARY KEY (id), 

    CONSTRAINT uk_student_management_candidate UNIQUE (candidate_key)

);

CREATE TABLE zhaolu_fact.authoritative_admission_stat (

    id BIGINT AUTO_INCREMENT NOT NULL, 

    year_no INTEGER NOT NULL, 

    college_name VARCHAR(255), 

    major_name VARCHAR(255) NOT NULL, 

    plan_count INTEGER DEFAULT '0' NOT NULL, 

    regular_admitted_count INTEGER DEFAULT '0' NOT NULL, 

    zhuan_admitted_count INTEGER DEFAULT '0' NOT NULL, 

    total_admitted_count INTEGER DEFAULT '0' NOT NULL, 

    source_file VARCHAR(512) NOT NULL, 

    data_version VARCHAR(64) NOT NULL, 

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    PRIMARY KEY (id), 

    CONSTRAINT uk_authoritative_admission_major UNIQUE (year_no, major_name, data_version)

);

CREATE TABLE zhaolu_dim.major_alias (

    id BIGINT AUTO_INCREMENT NOT NULL, 

    source_name VARCHAR(255) NOT NULL, 

    source_name_key VARCHAR(255) NOT NULL, 

    province_id BIGINT, 

    canonical_major_id BIGINT NOT NULL, 

    note TEXT, 

    is_active BOOLEAN DEFAULT true NOT NULL, 

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    PRIMARY KEY (id));

CREATE TABLE zhaolu_gov.canonicalization_event (

    id BIGINT AUTO_INCREMENT NOT NULL, 

    pipeline VARCHAR(32) NOT NULL, 

    entity_type VARCHAR(32) NOT NULL, 

    source_value VARCHAR(512) NOT NULL, 

    canonical_value VARCHAR(512) NOT NULL, 

    rule_code VARCHAR(64) NOT NULL, 

    scope_key VARCHAR(128) DEFAULT '' NOT NULL, 

    confidence NUMERIC(5, 4) DEFAULT '1.0' NOT NULL, 

    hit_count BIGINT DEFAULT '1' NOT NULL, 

    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    PRIMARY KEY (id)

);

CREATE TABLE zhaolu_fact.student_identity (

    id BIGINT AUTO_INCREMENT NOT NULL, 

    candidate_key VARCHAR(128) NOT NULL, 

    year_no INTEGER NOT NULL, 

    candidate_no VARCHAR(64) NOT NULL, 

    student_name VARCHAR(128) NOT NULL, 

    id_card VARCHAR(64), 

    phone VARCHAR(32), 

    address TEXT, 

    data_version VARCHAR(64) NOT NULL, 

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    PRIMARY KEY (id), 

    CONSTRAINT uk_student_identity_candidate_year UNIQUE (candidate_key, year_no)

);

ALTER TABLE zhaolu_fact.admission_record ADD COLUMN exam_score NUMERIC(8, 2);

ALTER TABLE zhaolu_dim.school ADD COLUMN school_short_name VARCHAR(128);

ALTER TABLE zhaolu_dim.school ADD COLUMN status VARCHAR(32) DEFAULT 'ACTIVE' NOT NULL;

ALTER TABLE zhaolu_dim.school ADD COLUMN timezone VARCHAR(64) DEFAULT 'Asia/Shanghai' NOT NULL;

ALTER TABLE zhaolu_dim.school ADD COLUMN settings JSON NOT NULL;

ALTER TABLE zhaolu_dim.school ADD COLUMN dbf_profile JSON NOT NULL;

ALTER TABLE zhaolu_dim.school ADD COLUMN knowledge_scope JSON NOT NULL;

ALTER TABLE zhaolu_dim.school ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL;

ALTER TABLE zhaolu_gov.dbf_import_batch ADD COLUMN school_id BIGINT;

ALTER TABLE zhaolu_gov.dbf_import_batch ADD COLUMN profile_id BIGINT;

CREATE TABLE zhaolu_sys.user_school (

    user_id BIGINT NOT NULL, 

    school_id BIGINT NOT NULL, 

    is_default BOOLEAN DEFAULT false NOT NULL, 

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    PRIMARY KEY (user_id, school_id)

);

CREATE TABLE zhaolu_gov.dbf_interface_profile (

    id BIGINT AUTO_INCREMENT NOT NULL, 

    school_id BIGINT NOT NULL, 

    profile_code VARCHAR(128) NOT NULL, 

    profile_name VARCHAR(255) NOT NULL, 

    schema_version VARCHAR(64) NOT NULL, 

    table_catalog JSON NOT NULL, 

    field_semantics JSON NOT NULL, 

    canonical_mapping JSON NOT NULL, 

    validation_rules JSON NOT NULL, 

    checksum VARCHAR(64), 

    is_active BOOLEAN DEFAULT true NOT NULL, 

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    PRIMARY KEY (id), 

    CONSTRAINT uk_dbf_profile_school_code UNIQUE (school_id, profile_code)

);

ALTER TABLE zhaolu_ai.knowledge_document ADD COLUMN school_id BIGINT;

ALTER TABLE zhaolu_ai.knowledge_document ADD COLUMN tags JSON NOT NULL;

ALTER TABLE zhaolu_ai.knowledge_document ADD COLUMN checksum VARCHAR(64);

ALTER TABLE zhaolu_ai.knowledge_document ADD COLUMN metadata JSON NOT NULL;

ALTER TABLE zhaolu_ai.knowledge_document ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL;

CREATE TABLE zhaolu_ai.agent_memory (

    id BIGINT AUTO_INCREMENT NOT NULL, 

    user_id BIGINT, 

    school_id BIGINT, 

    conversation_id BIGINT, 

    memory_type VARCHAR(64) NOT NULL, 

    memory_key VARCHAR(255) NOT NULL, 

    memory_value JSON NOT NULL, 

    summary TEXT NOT NULL, 

    confidence NUMERIC(5, 4) DEFAULT '0.8' NOT NULL, 

    importance NUMERIC(5, 4) DEFAULT '0.5' NOT NULL, 

    hit_count INTEGER DEFAULT '0' NOT NULL, 

    last_accessed_at TIMESTAMP, 

    expires_at TIMESTAMP, 

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    PRIMARY KEY (id), 

    CONSTRAINT uk_agent_memory_scope_key UNIQUE (user_id, school_id, memory_key)

);

CREATE TABLE zhaolu_ai.response_evaluation (

    id BIGINT AUTO_INCREMENT NOT NULL, 

    message_id BIGINT, 

    school_id BIGINT, 

    intent VARCHAR(128), 

    template_id BIGINT, 

    tool_names JSON NOT NULL, 

    self_check JSON NOT NULL, 

    score NUMERIC(5, 4) NOT NULL, 

    loss NUMERIC(5, 4) NOT NULL, 

    action VARCHAR(64) DEFAULT 'accepted' NOT NULL, 

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    PRIMARY KEY (id)

);

CREATE TABLE zhaolu_ai.prompt_template (

    id BIGINT AUTO_INCREMENT NOT NULL, 

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

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    PRIMARY KEY (id), 

    CONSTRAINT uk_prompt_template_scope UNIQUE (school_id, template_code, strategy_key)

);

CREATE TABLE zhaolu_ai.optimization_event (

    id BIGINT AUTO_INCREMENT NOT NULL, 

    school_id BIGINT, 

    template_id BIGINT, 

    signal_type VARCHAR(64) NOT NULL, 

    reward NUMERIC(6, 4) NOT NULL, 

    previous_weight NUMERIC(8, 4) NOT NULL, 

    new_weight NUMERIC(8, 4) NOT NULL, 

    learning_rate NUMERIC(8, 4) NOT NULL, 

    metadata JSON NOT NULL, 

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    PRIMARY KEY (id)

);

CREATE TABLE zhaolu_fact.enrollment_status (

    id BIGINT AUTO_INCREMENT NOT NULL, 

    candidate_key VARCHAR(128) NOT NULL, 

    year_no INTEGER NOT NULL, 

    candidate_no VARCHAR(64), 

    student_name VARCHAR(128), 

    is_enrolled BOOLEAN DEFAULT false NOT NULL, 

    enrolled_at DATE, 

    remark TEXT, 

    source_file VARCHAR(255), 

    data_version VARCHAR(64) NOT NULL, 

    raw_data JSON NOT NULL, 

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 

    PRIMARY KEY (id), 

    CONSTRAINT uk_enrollment_status_candidate_year UNIQUE (candidate_key, year_no)

);

CREATE DATABASE IF NOT EXISTS `zhaolu_analytics` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS zhaolu_analytics.mv_admissions_rollup (
    year_no INT NOT NULL,
    school_id BIGINT NOT NULL,
    school_name VARCHAR(255) NOT NULL,
    province_id BIGINT NOT NULL,
    province_name VARCHAR(64) NOT NULL,
    source_major_id BIGINT NOT NULL,
    source_major_name VARCHAR(255) NOT NULL,
    canonical_major_id BIGINT NOT NULL,
    canonical_major_name VARCHAR(255) NOT NULL,
    subject_id BIGINT NOT NULL,
    subject_name VARCHAR(64),
    plan_type_id BIGINT,
    plan_type_key BIGINT NOT NULL,
    plan_type_code VARCHAR(64) NOT NULL,
    batch_id BIGINT,
    plan_count BIGINT NOT NULL DEFAULT 0,
    admitted_count BIGINT NOT NULL DEFAULT 0,
    min_score DECIMAL(6,2),
    max_score DECIMAL(6,2),
    min_rank_no INT,
    data_version VARCHAR(64),
    PRIMARY KEY (
        year_no, school_id, province_id, source_major_id, canonical_major_id,
        subject_id, plan_type_key, batch_id
    ),
    KEY idx_mv_admissions_year_school_province_major (
        year_no, school_id, province_id, canonical_major_id
    ),
    KEY idx_mv_admissions_year_school_major (
        year_no, school_id, canonical_major_id
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET FOREIGN_KEY_CHECKS = 1;
