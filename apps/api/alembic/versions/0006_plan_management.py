
from alembic import op

revision = "0006_plan_management"
down_revision = "0005_student_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO sys.permission (permission_code, permission_name, permission_type)
        VALUES ('admissions:plan:manage', '填写和维护招生计划', 'BUTTON')
        ON CONFLICT (permission_code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO sys.role_permission (role_id, permission_id)
        SELECT r.id, p.id
        FROM sys.role r
        CROSS JOIN sys.permission p
        WHERE r.role_code IN ('SUPER_ADMIN', 'ADMISSION_DIRECTOR', 'DATA_ADMIN')
          AND p.permission_code = 'admissions:plan:manage'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM sys.role_permission
        WHERE permission_id IN (
            SELECT id FROM sys.permission WHERE permission_code = 'admissions:plan:manage'
        )
        """
    )
    op.execute(
        """
        DELETE FROM sys.permission
        WHERE permission_code = 'admissions:plan:manage'
        """
    )
