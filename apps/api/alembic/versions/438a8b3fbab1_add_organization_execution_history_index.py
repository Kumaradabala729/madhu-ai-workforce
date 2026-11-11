
"""add organization execution history index

Revision ID: 438a8b3fbab1
Revises: cd2f9f17cc1a
Create Date: 2026-11-11 12:58:12.499857
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "438a8b3fbab1"
down_revision: Union[str, Sequence[str], None] = "cd2f9f17cc1a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_execution_org_created_id
        ON ai_employee_executions
        (organization_id, created_at, id)
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_execution_org_created_id",
        table_name="ai_employee_executions",
    )
