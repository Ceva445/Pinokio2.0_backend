"""Add observer role to user_role enum

Revision ID: a1c3e5f7b9d2
Revises: e7f8a9b0c1d2
Create Date: 2026-09-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a1c3e5f7b9d2'
down_revision: Union[str, Sequence[str], None] = 'e7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Postgres 12+ pozwala dodać wartość enuma wewnątrz transakcji, dopóki nie
    # użyjemy jej w tej samej transakcji — a tutaj tylko ją zakładamy.
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'observer'")


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres nie umie usunąć wartości z enuma. Zdjęcie 'observer' oznaczałoby
    # przebudowę typu wraz z kolumną users.role, co przy istniejących kontach
    # obserwatorów kasowałoby dane. Zostawiamy wartość w typie — jest nieszkodliwa,
    # dopóki żaden użytkownik jej nie ma.
    pass
