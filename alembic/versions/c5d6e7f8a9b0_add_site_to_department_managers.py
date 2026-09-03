"""Link department managers to the sites lookup table

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-09-03 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5d6e7f8a9b0'
down_revision: Union[str, Sequence[str], None] = 'b4c5d6e7f8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('department_managers', sa.Column('site_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_department_managers_site_id_sites',
        'department_managers', 'sites', ['site_id'], ['id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'fk_department_managers_site_id_sites', 'department_managers', type_='foreignkey'
    )
    op.drop_column('department_managers', 'site_id')
