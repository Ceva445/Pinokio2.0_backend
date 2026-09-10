"""Add source marker to transactions

Revision ID: c5e7a9b1d3f6
Revises: a1c3e5f7b9d2
Create Date: 2026-09-10 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c5e7a9b1d3f6'
down_revision: Union[str, Sequence[str], None] = 'a1c3e5f7b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Kolumna zostaje pusta dla całej dotychczasowej historii — NULL znaczy
    # "karta na czytniku", czyli dokładnie to, czym były wszystkie te wiersze.
    op.add_column(
        "transactions",
        sa.Column("source", sa.String(length=16), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("transactions", "source")
