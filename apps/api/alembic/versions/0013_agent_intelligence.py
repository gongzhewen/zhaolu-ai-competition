
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_agent_intelligence"
down_revision = "0012_ultimate_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("school", sa.Column("school_short_name", sa.String(length=128)), schema="dim")
    op.add_column("school", sa.Column("status", sa.String(length=32), server_default="ACTIVE", nullable=False), schema="dim")
    op.add_column("school", sa.Column("timezone", sa.String(length=64), server_default="Asia/Shanghai", nullable=False), schema="dim")
    op.add_column("school", sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False), schema="dim")
    op.add_column("school", sa.Column("dbf_profile", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False), schema="dim")
    op.add_column("school", sa.Column("knowledge_scope", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False), schema="dim")
    op.add_column("school", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), schema="dim")

    op.add_column("dbf_import_batch", sa.Column("school_id", sa.BigInteger()), schema="gov")
    op.add_column("dbf_import_batch", sa.Column("profile_id", sa.BigInteger()), schema="gov")
    op.create_foreign_key(
        "fk_dbf_import_batch_school",
        "dbf_import_batch",
        "school",
        ["school_id"],
        ["id"],
        source_schema="gov",
        referent_schema="dim",
    )

    op.create_table(
        "user_school",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("school_id", sa.BigInteger(), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["sys.user_account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["school_id"], ["dim.school.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "school_id"),
        schema="sys",
    )

    op.create_table(
        "dbf_interface_profile",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("school_id", sa.BigInteger(), nullable=False),
        sa.Column("profile_code", sa.String(length=128), nullable=False),
        sa.Column("profile_name", sa.String(length=255), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("table_catalog", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("field_semantics", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("canonical_mapping", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("validation_rules", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("checksum", sa.String(length=64)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["school_id"], ["dim.school.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("school_id", "profile_code", name="uk_dbf_profile_school_code"),
        schema="gov",
    )

    op.add_column("knowledge_document", sa.Column("school_id", sa.BigInteger()), schema="ai")
    op.add_column("knowledge_document", sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False), schema="ai")
    op.add_column("knowledge_document", sa.Column("checksum", sa.String(length=64)), schema="ai")
    op.add_column("knowledge_document", sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False), schema="ai")
    op.add_column("knowledge_document", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), schema="ai")
    op.create_foreign_key(
        "fk_knowledge_document_school",
        "knowledge_document",
        "school",
        ["school_id"],
        ["id"],
        source_schema="ai",
        referent_schema="dim",
    )
    op.create_index("idx_knowledge_document_school_status", "knowledge_document", ["school_id", "status"], schema="ai")

    op.create_table(
        "agent_memory",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger()),
        sa.Column("school_id", sa.BigInteger()),
        sa.Column("conversation_id", sa.BigInteger()),
        sa.Column("memory_type", sa.String(length=64), nullable=False),
        sa.Column("memory_key", sa.String(length=255), nullable=False),
        sa.Column("memory_value", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), server_default="0.8", nullable=False),
        sa.Column("importance", sa.Numeric(5, 4), server_default="0.5", nullable=False),
        sa.Column("hit_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["sys.user_account.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["school_id"], ["dim.school.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["ai.conversation.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", "school_id", "memory_key", name="uk_agent_memory_scope_key"),
        schema="ai",
    )
    op.create_index("idx_agent_memory_query", "agent_memory", ["user_id", "school_id", "memory_type"], schema="ai")

    op.create_table(
        "response_evaluation",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("message_id", sa.BigInteger()),
        sa.Column("school_id", sa.BigInteger()),
        sa.Column("intent", sa.String(length=128)),
        sa.Column("template_id", sa.BigInteger()),
        sa.Column("tool_names", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("self_check", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("score", sa.Numeric(5, 4), nullable=False),
        sa.Column("loss", sa.Numeric(5, 4), nullable=False),
        sa.Column("action", sa.String(length=64), server_default="accepted", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["ai.message.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["school_id"], ["dim.school.id"], ondelete="SET NULL"),
        schema="ai",
    )
    op.create_index("idx_response_evaluation_school_created", "response_evaluation", ["school_id", "created_at"], schema="ai")

    op.create_table(
        "prompt_template",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("template_code", sa.String(length=128), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("school_id", sa.BigInteger()),
        sa.Column("template_name", sa.String(length=255), nullable=False),
        sa.Column("template_text", sa.Text(), nullable=False),
        sa.Column("strategy_key", sa.String(length=64), nullable=False),
        sa.Column("weight", sa.Numeric(8, 4), server_default="1.0", nullable=False),
        sa.Column("usage_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("success_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("version_no", sa.String(length=64), server_default="v1", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["school_id"], ["dim.school.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("school_id", "template_code", "strategy_key", name="uk_prompt_template_scope"),
        schema="ai",
    )

    op.create_foreign_key(
        "fk_response_evaluation_template",
        "response_evaluation",
        "prompt_template",
        ["template_id"],
        ["id"],
        source_schema="ai",
        referent_schema="ai",
        ondelete="SET NULL",
    )

    op.create_table(
        "optimization_event",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("school_id", sa.BigInteger()),
        sa.Column("template_id", sa.BigInteger()),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("reward", sa.Numeric(6, 4), nullable=False),
        sa.Column("previous_weight", sa.Numeric(8, 4), nullable=False),
        sa.Column("new_weight", sa.Numeric(8, 4), nullable=False),
        sa.Column("learning_rate", sa.Numeric(8, 4), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["school_id"], ["dim.school.id"], ondelete="SET NULL"),
        schema="ai",
    )

    op.execute(
        sa.text(
            """
            INSERT INTO sys.user_school (user_id, school_id, is_default)
            SELECT u.id, s.id, TRUE
            FROM sys.user_account u
            CROSS JOIN LATERAL (SELECT id FROM dim.school ORDER BY id LIMIT 1) s
            WHERE u.username IN ('admin', 'ultimate_admin')
            ON CONFLICT DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO ai.prompt_template (
                template_code, task_type, school_id, template_name, template_text,
                strategy_key, weight, version_no
            )
            VALUES
                ('decision_v1', 'decision', NULL, '决策结论模板',
                 '先给出明确结论，再列出关键数据依据、风险、适用条件和分步执行建议。所有数字必须来自工具结果。',
                 'evidence_first', 1.0, 'v1'),
                ('analysis_v1', 'analysis', NULL, '数据分析模板',
                 '先概述数据范围，再分析关键变化和原因，最后给出管理建议。所有数字必须来自工具结果。',
                 'evidence_first', 1.0, 'v1'),
                ('lookup_v1', 'lookup', NULL, '事实查询模板',
                 '直接回答事实，注明筛选条件、数据年度和数据来源，不补充无法由工具支持的判断。',
                 'grounded_answer', 1.0, 'v1'),
                ('policy_v1', 'policy', NULL, '政策问答模板',
                 '依据招生知识库回答，给出结论、适用边界和来源；无法确认时明确要求咨询省考试院或学校招生办。',
                 'citation_first', 1.0, 'v1'),
                ('default_v1', 'default', NULL, '通用回答模板',
                 '优先使用确定性数据工具，清晰回答；数据不足时说明缺失项，不得编造。',
                 'grounded_answer', 1.0, 'v1')
            ON CONFLICT DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_table("optimization_event", schema="ai")
    op.drop_constraint("fk_response_evaluation_template", "response_evaluation", schema="ai", type_="foreignkey")
    op.drop_table("prompt_template", schema="ai")
    op.drop_index("idx_response_evaluation_school_created", table_name="response_evaluation", schema="ai")
    op.drop_table("response_evaluation", schema="ai")
    op.drop_index("idx_agent_memory_query", table_name="agent_memory", schema="ai")
    op.drop_table("agent_memory", schema="ai")
    op.drop_index("idx_knowledge_document_school_status", table_name="knowledge_document", schema="ai")
    op.drop_constraint("fk_knowledge_document_school", "knowledge_document", schema="ai", type_="foreignkey")
    op.drop_column("knowledge_document", "updated_at", schema="ai")
    op.drop_column("knowledge_document", "metadata", schema="ai")
    op.drop_column("knowledge_document", "checksum", schema="ai")
    op.drop_column("knowledge_document", "tags", schema="ai")
    op.drop_column("knowledge_document", "school_id", schema="ai")
    op.drop_table("dbf_interface_profile", schema="gov")
    op.drop_table("user_school", schema="sys")
    op.drop_constraint("fk_dbf_import_batch_school", "dbf_import_batch", schema="gov", type_="foreignkey")
    op.drop_column("dbf_import_batch", "profile_id", schema="gov")
    op.drop_column("dbf_import_batch", "school_id", schema="gov")
    op.drop_column("school", "updated_at", schema="dim")
    op.drop_column("school", "knowledge_scope", schema="dim")
    op.drop_column("school", "dbf_profile", schema="dim")
    op.drop_column("school", "settings", schema="dim")
    op.drop_column("school", "timezone", schema="dim")
    op.drop_column("school", "status", schema="dim")
    op.drop_column("school", "school_short_name", schema="dim")

