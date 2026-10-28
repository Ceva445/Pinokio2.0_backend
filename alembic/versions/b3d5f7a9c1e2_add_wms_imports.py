"""add wms_imports

Revision ID: b3d5f7a9c1e2
Revises: f9b2d4e6a8c1
Create Date: 2026-10-28

Paczki ruchów przysyłane przez skrypt z serwera WMS. Trzymamy surowe wiersze,
bo zestawienie liczy się przy otwieraniu raportu — z aktualnego stanu wydań.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b3d5f7a9c1e2'
down_revision: Union[str, Sequence[str], None] = 'f9b2d4e6a8c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wms_imports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False,
                  server_default="push"),
        sa.Column("origin", sa.String(length=100), nullable=True),
        sa.Column("rows_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("period_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wms_imports_received_at", "wms_imports", ["received_at"])


def downgrade() -> None:
    op.drop_index("ix_wms_imports_received_at", table_name="wms_imports")
    op.drop_table("wms_imports")
