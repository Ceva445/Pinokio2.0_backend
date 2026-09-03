"""Link employees to the sites lookup table

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-09-03 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, Sequence[str], None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('employees', sa.Column('site_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_employees_site_id_sites', 'employees', 'sites', ['site_id'], ['id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_employees_site_id_sites', 'employees', type_='foreignkey')
    op.drop_column('employees', 'site_id')
