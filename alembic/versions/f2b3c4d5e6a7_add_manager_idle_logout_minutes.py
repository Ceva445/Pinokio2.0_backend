"""Add configurable manager idle-logout timeout

Revision ID: f2b3c4d5e6a7
Revises: e1a2b3c4d5f6
Create Date: 2026-09-02 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2b3c4d5e6a7'
down_revision: Union[str, Sequence[str], None] = 'e1a2b3c4d5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'system_config',
        sa.Column(
            'manager_idle_logout_minutes',
            sa.Integer(),
            nullable=False,
            server_default='15',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('system_config', 'manager_idle_logout_minutes')
