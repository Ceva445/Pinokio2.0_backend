"""Add users.sessions_valid_from

Revision ID: f9b2d4e6a8c1
Revises: e8a1c3d5f7b9
Create Date: 2026-09-11 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f9b2d4e6a8c1'
down_revision: Union[str, Sequence[str], None] = 'e8a1c3d5f7b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Unieważnianie sesji trzymało się dotąd wyłącznie pamięci procesu: zbiór
    # revoked_tokens i słownik aktywnych sesji. Po każdym restarcie backendu
    # znikały, a token w przeglądarce żył dalej swoje dwanaście godzin — admin
    # nie miał czym wyrzucić takiego użytkownika, bo panel go nie widział.
    #
    # Ta kolumna to granica: token wystawiony wcześniej jest nieważny,
    # niezależnie od tego, co pamięta proces.
    op.add_column(
        'users',
        sa.Column('sessions_valid_from', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'sessions_valid_from')
