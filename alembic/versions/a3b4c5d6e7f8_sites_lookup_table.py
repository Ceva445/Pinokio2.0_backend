"""Replace SiteType enum with a sites lookup table

Revision ID: a3b4c5d6e7f8
Revises: f2b3c4d5e6a7
Create Date: 2026-09-03 12:00:00.000000

Мігрує devices.site (enum sitetype) → devices.site_id (FK на sites).
Наявні значення переносяться за назвою, тому жоден пристрій не втрачає site.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, Sequence[str], None] = 'f2b3c4d5e6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED_SITES = ["EMAG", "XD", "STOCK", "KONTROLA", "PRZYJECIA_445"]


def upgrade() -> None:
    """Upgrade schema."""
    sites = op.create_table(
        'sites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index('ix_sites_name', 'sites', ['name'])

    # 1. посіяти наявні значення enum як рядки довідника
    op.bulk_insert(sites, [{"name": n, "description": None, "enabled": True} for n in SEED_SITES])

    # 2. нова колонка + FK
    op.add_column('devices', sa.Column('site_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_devices_site_id_sites', 'devices', 'sites', ['site_id'], ['id']
    )

    # 3. перенести дані зі старої enum-колонки за назвою
    op.execute(
        "UPDATE devices d SET site_id = s.id "
        "FROM sites s WHERE s.name = d.site::text"
    )

    # 4. прибрати стару колонку і тип
    op.drop_column('devices', 'site')
    op.execute("DROP TYPE IF EXISTS sitetype")


def downgrade() -> None:
    """Downgrade schema."""
    sitetype = sa.Enum(*SEED_SITES, name='sitetype')
    sitetype.create(op.get_bind(), checkfirst=True)

    op.add_column('devices', sa.Column('site', sitetype, nullable=True))
    op.execute(
        "UPDATE devices d SET site = s.name::sitetype "
        "FROM sites s WHERE s.id = d.site_id "
        "AND s.name IN ('EMAG','XD','STOCK','KONTROLA','PRZYJECIA_445')"
    )

    op.drop_constraint('fk_devices_site_id_sites', 'devices', type_='foreignkey')
    op.drop_column('devices', 'site_id')
    op.drop_index('ix_sites_name', table_name='sites')
    op.drop_table('sites')
