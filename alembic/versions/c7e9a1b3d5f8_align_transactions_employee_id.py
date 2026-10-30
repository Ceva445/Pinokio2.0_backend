"""align transactions.employee_id

Revision ID: c7e9a1b3d5f8
Revises: b3d5f7a9c1e2
Create Date: 2026-10-30

Produkcja ma w transactions kolumnę employee_id, a migracje budowały user_id
(tak ją założyło d2fc76fe83d3). Ktoś przemianował ją kiedyś ręcznie i nigdy
nie zapisał tego w migracjach, więc świeża baza wychodziła z nazwą, której
kod nie zna — aplikacja na nowej instalacji po prostu się wywracała.

Migracja jest obojętna tam, gdzie kolumna już nazywa się employee_id, czyli
na produkcji nie zmienia niczego. Nie przepisujemy starej migracji, bo
produkcja dawno ją ma odhaczoną.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c7e9a1b3d5f8'
down_revision: Union[str, Sequence[str], None] = 'b3d5f7a9c1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABELA = "transactions"


def _kolumny(inspector) -> set:
    return {kolumna["name"] for kolumna in inspector.get_columns(TABELA)}


def _klucze_obce(inspector) -> set:
    return {klucz["name"] for klucz in inspector.get_foreign_keys(TABELA)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    kolumny = _kolumny(inspector)

    if "employee_id" in kolumny:
        return                      # produkcja: nazwa już właściwa

    if "user_id" in kolumny:
        op.alter_column(TABELA, "user_id", new_column_name="employee_id")
        # Nazwa ograniczenia nie zmienia się razem z kolumną, a zostawiona
        # myli przy następnym porównaniu schematów.
        if "transactions_user_id_fkey" in _klucze_obce(sa.inspect(op.get_bind())):
            op.execute("ALTER TABLE transactions RENAME CONSTRAINT "
                       "transactions_user_id_fkey TO transactions_employee_id_fkey")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "employee_id" not in _kolumny(inspector):
        return

    if "transactions_employee_id_fkey" in _klucze_obce(inspector):
        op.execute("ALTER TABLE transactions RENAME CONSTRAINT "
                   "transactions_employee_id_fkey TO transactions_user_id_fkey")
    op.alter_column(TABELA, "employee_id", new_column_name="user_id")
