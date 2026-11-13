"""Borrowed guest cards for employees who left their own card at home

Revision ID: b5d7f9a1c3e4
Revises: a4c6e8b1d3f5
Create Date: 2026-11-13 10:00:00.000000

Pożyczka jest osobnym wierszem, żeby employees.rfid zostało nietknięte:
własna karta działa dalej, a historia i statystyka zostają przy jednym
pracowniku. Obok leci próg ważności takiej karty (domyślnie 12 godzin),
osobny od terminu karty pracownika tymczasowego.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5d7f9a1c3e4'
down_revision: Union[str, Sequence[str], None] = 'a4c6e8b1d3f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'borrowed_cards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('guest_id', sa.Integer(), nullable=False),
        sa.Column('rfid', sa.String(length=64), nullable=False),
        sa.Column('issued_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('returned_at', sa.DateTime(), nullable=True),
        sa.Column('returned_reason', sa.String(length=16), nullable=True),
        sa.Column('issued_by_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.ForeignKeyConstraint(['guest_id'], ['guests.id'], ),
        sa.ForeignKeyConstraint(['issued_by_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_borrowed_cards_employee_id', 'borrowed_cards', ['employee_id'])
    op.create_index('ix_borrowed_cards_guest_id', 'borrowed_cards', ['guest_id'])
    op.create_index('ix_borrowed_cards_rfid', 'borrowed_cards', ['rfid'])

    op.add_column(
        'system_config',
        sa.Column(
            'borrowed_card_duration_hours',
            sa.Integer(),
            nullable=False,
            server_default='12',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('system_config', 'borrowed_card_duration_hours')
    op.drop_index('ix_borrowed_cards_rfid', table_name='borrowed_cards')
    op.drop_index('ix_borrowed_cards_guest_id', table_name='borrowed_cards')
    op.drop_index('ix_borrowed_cards_employee_id', table_name='borrowed_cards')
    op.drop_table('borrowed_cards')
