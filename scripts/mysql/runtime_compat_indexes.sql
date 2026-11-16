-- Runtime compatibility indexes for zhaolu-ai-v2 MySQL deployments.
-- Run once on an existing database after updating the application.

ALTER TABLE zhaolu_fact.plan
    ADD COLUMN plan_type_key BIGINT GENERATED ALWAYS AS (COALESCE(plan_type_id, 0)) STORED;

ALTER TABLE zhaolu_fact.plan
    ADD UNIQUE KEY uk_plan_natural (
        year_id, school_id, province_id, batch_id, subject_id, major_id,
        plan_type_key, data_version
    );

ALTER TABLE zhaolu_fact.plan
    ADD KEY idx_plan_dimensions (year_id, school_id, province_id, batch_id, subject_id, major_id);

ALTER TABLE zhaolu_fact.plan
    ADD KEY idx_plan_school_year_province_major (school_id, year_id, province_id, major_id);

ALTER TABLE zhaolu_fact.admission_summary
    ADD UNIQUE KEY uk_admission_summary_plan_version (plan_id, data_version);

ALTER TABLE zhaolu_fact.admission_summary
    ADD KEY idx_admission_summary_plan (plan_id, data_version);

ALTER TABLE zhaolu_fact.admission_record
    ADD KEY idx_admission_record_dimensions (year_id, province_id, major_id, subject_id);

ALTER TABLE zhaolu_fact.score_line
    ADD KEY idx_score_line_dimensions (year_id, province_id, batch_id, subject_id, major_id);

ALTER TABLE zhaolu_dim.major_alias
    ADD COLUMN province_scope_id BIGINT GENERATED ALWAYS AS (COALESCE(province_id, 0)) STORED;

ALTER TABLE zhaolu_dim.major_alias
    ADD UNIQUE KEY uk_major_alias_scope (source_name_key, province_scope_id);

ALTER TABLE zhaolu_dim.major_alias
    ADD KEY idx_major_alias_canonical (canonical_major_id, is_active);

ALTER TABLE zhaolu_gov.canonicalization_event
    ADD COLUMN event_key CHAR(64)
    GENERATED ALWAYS AS (
        SHA2(CONCAT_WS('|', pipeline, entity_type, source_value, canonical_value, scope_key), 256)
    ) STORED;

ALTER TABLE zhaolu_gov.canonicalization_event
    ADD UNIQUE KEY uk_canonicalization_event (event_key);

ALTER TABLE zhaolu_gov.canonicalization_event
    ADD KEY idx_canonicalization_event_type (entity_type, last_seen_at);

ALTER TABLE zhaolu_gov.data_issue
    ADD KEY idx_quality_issue_status (issue_status, created_at);

ALTER TABLE zhaolu_gov.import_field_mapping
    ADD KEY ix_import_field_mapping_job (job_id);

ALTER TABLE zhaolu_gov.import_record
    ADD KEY ix_import_record_job_status (job_id, status);

ALTER TABLE zhaolu_gov.etl_job
    ADD KEY ix_etl_job_status (job_status, created_at);

ALTER TABLE zhaolu_gov.dbf_import_table
    ADD KEY ix_dbf_import_table_batch (batch_id);

ALTER TABLE zhaolu_gov.dbf_import_row
    ADD KEY ix_dbf_import_row_batch_table (batch_id, table_id);

ALTER TABLE zhaolu_dim.school
    ADD KEY idx_school_province_status (province_id, status);

ALTER TABLE zhaolu_fact.candidate_profile
    ADD KEY idx_candidate_profile_key (candidate_key);

ALTER TABLE zhaolu_fact.candidate_profile
    ADD KEY idx_candidate_profile_region (year_no, region_code);

ALTER TABLE zhaolu_fact.exam_subject_score
    ADD KEY idx_exam_subject_score_candidate (candidate_key, subject_code);

ALTER TABLE zhaolu_fact.major_choice
    ADD KEY idx_major_choice_candidate (candidate_key, choice_order);

ALTER TABLE zhaolu_fact.candidate_resume
    ADD KEY idx_candidate_resume_candidate (candidate_key, start_date);

ALTER TABLE zhaolu_fact.medical_summary
    ADD KEY idx_medical_summary_candidate (candidate_key);

ALTER TABLE zhaolu_fact.student_management
    ADD KEY idx_student_management_status (student_status, follow_up_status);

ALTER TABLE zhaolu_fact.student_management
    ADD KEY idx_student_management_owner (owner_name);

ALTER TABLE zhaolu_fact.authoritative_admission_stat
    ADD KEY idx_authoritative_admission_year (year_no, major_name);

ALTER TABLE zhaolu_fact.student_identity
    ADD KEY idx_student_identity_year (year_no, candidate_no);

ALTER TABLE zhaolu_fact.enrollment_status
    ADD KEY idx_enrollment_status_year_enrolled (year_no, is_enrolled);

ALTER TABLE zhaolu_fact.enrollment_status
    ADD KEY idx_enrollment_status_candidate_no (candidate_no);

ALTER TABLE zhaolu_ai.knowledge_chunk
    ADD KEY idx_knowledge_chunk_document (document_id, chunk_index);

ALTER TABLE zhaolu_ai.knowledge_document
    ADD UNIQUE KEY uk_knowledge_document_checksum (checksum);

ALTER TABLE zhaolu_ai.knowledge_document
    ADD KEY idx_knowledge_document_school_status (school_id, status);

ALTER TABLE zhaolu_ai.message
    ADD KEY idx_ai_message_conversation (conversation_id, created_at);

ALTER TABLE zhaolu_ai.agent_memory
    ADD KEY idx_agent_memory_query (user_id, school_id, memory_type);

ALTER TABLE zhaolu_ai.response_evaluation
    ADD KEY idx_response_evaluation_school_created (school_id, created_at);

ALTER TABLE zhaolu_sys.audit_log
    ADD KEY idx_audit_log_created (created_at);

ALTER TABLE zhaolu_sys.audit_log
    ADD KEY idx_audit_log_user (user_id, created_at);
