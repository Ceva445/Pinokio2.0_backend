"""employees.rfid moze byc puste

Revision ID: d1e3f5a7b9c2
Revises: c7e9a1b3d5f8
Create Date: 2026-11-04

Karta gościa po terminie wraca do puli, a pracownik zostaje bez karty — jego
historia i login WMS mają przetrwać, żeby tego samego człowieka dać się
zatrudnić ponownie zamiast zakładać drugi rekord z dopiskiem w loginie.

Unikalny indeks zostaje: i Postgres, i sqlite dopuszczają w nim wiele NULL-i,
więc kilku pracowników bez karty współistnieje bez kolizji.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd1e3f5a7b9c2'
down_revision: Union[str, Sequence[str], None] = 'c7e9a1b3d5f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rfid(inspector):
    for kolumna in inspector.get_columns("employees"):
        if kolumna["name"] == "rfid":
            return kolumna
    return None


def upgrade() -> None:
    kolumna = _rfid(sa.inspect(op.get_bind()))
    if kolumna is None or kolumna["nullable"]:
        return
    op.alter_column("employees", "rfid", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    # Pracownicy bez karty muszą zniknąć z kolumny, inaczej NOT NULL nie wróci.
    op.execute("DELETE FROM employees WHERE rfid IS NULL")
    op.alter_column("employees", "rfid", existing_type=sa.String(), nullable=False)
