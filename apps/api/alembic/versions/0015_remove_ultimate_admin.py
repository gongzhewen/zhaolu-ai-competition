
import sqlalchemy as sa
from alembic import op

revision = "0015_remove_ultimate_admin"
down_revision = "0014_enrollment_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            WITH target AS (
                SELECT id FROM sys.user_account WHERE username = 'ultimate_admin'
            ), conversations AS (
                SELECT id FROM ai.conversation WHERE user_id IN (SELECT id FROM target)
            )
            DELETE FROM ai.feedback
            WHERE user_id IN (SELECT id FROM target)
               OR message_id IN (
                   SELECT id FROM ai.message WHERE conversation_id IN (SELECT id FROM conversations)
               )
            """
        )
    )
    op.execute(
        sa.text(
            """
            WITH target AS (
                SELECT id FROM sys.user_account WHERE username = 'ultimate_admin'
            ), conversations AS (
                SELECT id FROM ai.conversation WHERE user_id IN (SELECT id FROM target)
            )
            DELETE FROM ai.response_evaluation
            WHERE message_id IN (
                SELECT id FROM ai.message WHERE conversation_id IN (SELECT id FROM conversations)
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            WITH target AS (
                SELECT id FROM sys.user_account WHERE username = 'ultimate_admin'
            ), conversations AS (
                SELECT id FROM ai.conversation WHERE user_id IN (SELECT id FROM target)
            )
            DELETE FROM ai.tool_call WHERE conversation_id IN (SELECT id FROM conversations)
            """
        )
    )
    op.execute(
        sa.text(
            """
            WITH target AS (
                SELECT id FROM sys.user_account WHERE username = 'ultimate_admin'
            ), conversations AS (
                SELECT id FROM ai.conversation WHERE user_id IN (SELECT id FROM target)
            )
            DELETE FROM ai.agent_memory
            WHERE user_id IN (SELECT id FROM target)
               OR conversation_id IN (SELECT id FROM conversations)
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM ai.message
            WHERE conversation_id IN (
                SELECT id FROM ai.conversation
                WHERE user_id IN (SELECT id FROM sys.user_account WHERE username = 'ultimate_admin')
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM ai.conversation
            WHERE user_id IN (SELECT id FROM sys.user_account WHERE username = 'ultimate_admin')
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM sys.user_school
            WHERE user_id IN (SELECT id FROM sys.user_account WHERE username = 'ultimate_admin')
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM sys.user_role
            WHERE user_id IN (SELECT id FROM sys.user_account WHERE username = 'ultimate_admin')
               OR role_id IN (SELECT id FROM sys.role WHERE role_code = 'ULTIMATE_ADMIN')
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM sys.role_permission
            WHERE role_id IN (SELECT id FROM sys.role WHERE role_code = 'ULTIMATE_ADMIN')
            """
        )
    )
    op.execute(sa.text("DELETE FROM sys.user_account WHERE username = 'ultimate_admin'"))
    op.execute(sa.text("DELETE FROM sys.role WHERE role_code = 'ULTIMATE_ADMIN'"))


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO sys.role (role_code, role_name)
            VALUES ('ULTIMATE_ADMIN', '终极管理员（展示脱敏）')
            ON CONFLICT (role_code) DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO sys.user_account (username, password_hash, display_name, status)
            VALUES (
                'ultimate_admin',
                'pbkdf2_sha256$260000$HK7RqZUYl7_XH5-fwsSl8w$hKpS2T2eBEHRoqX1FWUGAo1c9SnFwYTHMEDEyTrd_-8',
                '赛事展示管理员',
                'ACTIVE'
            )
            ON CONFLICT (username) DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO sys.user_role (user_id, role_id)
            SELECT u.id, r.id
            FROM sys.user_account u
            CROSS JOIN sys.role r
            WHERE u.username = 'ultimate_admin' AND r.role_code = 'ULTIMATE_ADMIN'
            ON CONFLICT DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO sys.role_permission (role_id, permission_id)
            SELECT r.id, p.id
            FROM sys.role r CROSS JOIN sys.permission p
            WHERE r.role_code = 'ULTIMATE_ADMIN'
            ON CONFLICT DO NOTHING
            """
        )
    )
