"""Add manager who authorized the device handover to registration transactions

Revision ID: e1a2b3c4d5f6
Revises: d9f2a3b4c5e6
Create Date: 2026-09-01 21:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1a2b3c4d5f6'
down_revision: Union[str, Sequence[str], None] = 'd9f2a3b4c5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'transactions',
        sa.Column('manager_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_transactions_manager_id_users',
        'transactions', 'users',
        ['manager_id'], ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'fk_transactions_manager_id_users', 'transactions', type_='foreignkey'
    )
    op.drop_column('transactions', 'manager_id')
