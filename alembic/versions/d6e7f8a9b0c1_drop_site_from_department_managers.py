"""Drop the redundant site_id from department managers

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-09-03 22:00:00.000000

Dział i site to to samo pojęcie — okazało się, że osobne pole site_id
dublowało kolumnę department. Wracamy do jednej kolumny (department),
która przechowuje nazwę site albo wartość specjalną "ALL".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd6e7f8a9b0c1'
down_revision: Union[str, Sequence[str], None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(
        'fk_department_managers_site_id_sites', 'department_managers', type_='foreignkey'
    )
    op.drop_column('department_managers', 'site_id')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('department_managers', sa.Column('site_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_department_managers_site_id_sites',
        'department_managers', 'sites', ['site_id'], ['id']
    )
