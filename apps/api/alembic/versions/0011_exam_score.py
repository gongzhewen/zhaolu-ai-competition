
import sqlalchemy as sa
from alembic import op

revision = "0011_exam_score"
down_revision = "0010_student_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("admission_record", sa.Column("exam_score", sa.Numeric(8, 2)), schema="fact")


def downgrade() -> None:
    op.drop_column("admission_record", "exam_score", schema="fact")
