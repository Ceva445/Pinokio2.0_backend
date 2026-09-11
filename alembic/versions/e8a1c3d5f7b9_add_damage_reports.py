"""Add damage_reports

Revision ID: e8a1c3d5f7b9
Revises: d7f9b2c4e6a8
Create Date: 2026-09-11 10:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e8a1c3d5f7b9'
down_revision: Union[str, Sequence[str], None] = 'd7f9b2c4e6a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'damage_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column(
            'timestamp', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False
        ),
        sa.Column('device_id', sa.Integer(), nullable=False),
        # Zgłaszający i posiadacz mogą zniknąć z systemu; protokół zostaje.
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('employee_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(
        op.f('ix_damage_reports_device_id'), 'damage_reports', ['device_id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_damage_reports_device_id'), table_name='damage_reports')
    op.drop_table('damage_reports')
