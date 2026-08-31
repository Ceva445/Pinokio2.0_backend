"""Add email notification schedule config

Revision ID: c8e1f2a3b4d5
Revises: b7f3c1a9d2e4
Create Date: 2026-08-31 10:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8e1f2a3b4d5'
down_revision: Union[str, Sequence[str], None] = 'b7f3c1a9d2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'system_config',
        sa.Column(
            'email_notifications_enabled',
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        'system_config',
        sa.Column(
            'email_send_times',
            sa.String(),
            nullable=False,
            server_default='09:00,15:00',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('system_config', 'email_send_times')
    op.drop_column('system_config', 'email_notifications_enabled')
