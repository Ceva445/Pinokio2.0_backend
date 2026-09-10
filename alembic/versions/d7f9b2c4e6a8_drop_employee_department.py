"""Drop employees.department

Revision ID: d7f9b2c4e6a8
Revises: c5e7a9b1d3f6
Create Date: 2026-09-11 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd7f9b2c4e6a8'
down_revision: Union[str, Sequence[str], None] = 'c5e7a9b1d3f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Dział pracownika był wolnym tekstem obok site_id, które wskazuje ten sam
    # magazyn. Dwa źródła tej samej prawdy rozjeżdżały się: "Stock" i "STOCK"
    # stawały się osobnymi wierszami na dashboardzie, a mail o niezwróconym
    # sprzęcie nie znajdował kierownika, bo szukał po dokładnym ciągu.
    #
    # Site_id jest wypełnione dla wszystkich pracowników, a cała logika czyta
    # już wyłącznie słownik sites — kolumna nie ma czego trzymać.
    op.drop_index(op.f('ix_employees_department'), table_name='employees')
    op.drop_column('employees', 'department')


def downgrade() -> None:
    """Downgrade schema."""
    # Kolumna wraca pusta: wartości da się odtworzyć tylko z kopii bazy.
    op.add_column(
        'employees',
        sa.Column('department', sa.String(), nullable=True)
    )
    op.create_index(op.f('ix_employees_department'), 'employees', ['department'])
