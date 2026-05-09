"""Add site field to devices table

Revision ID: g9d3e8f7a6c5
Revises: f8c2d9e3a1b4
Create Date: 2026-05-09 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "g9d3e8f7a6c5"
down_revision: Union[str, Sequence[str], None] = "65f13e9bb6b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


site_enum = sa.Enum(
    "EMAG",
    "XD",
    "STOCK",
    "KONTROLA",
    "445 (przyjecia)",
    name="sitetype",
)


def upgrade() -> None:
    """Upgrade schema."""

    # Create ENUM type
    site_enum.create(op.get_bind(), checkfirst=True)

    # Add column with temporary default for existing rows
    op.add_column(
        "devices",
        sa.Column(
            "site",
            site_enum,
            nullable=True,
            server_default="EMAG",
        ),
    )

    # Remove default after migration
    op.alter_column(
        "devices",
        "site",
        server_default=None,
    )


def downgrade() -> None:
    """Downgrade schema."""

    # Remove column
    op.drop_column("devices", "site")
    
    # Drop ENUM type
    site_enum.drop(op.get_bind(), checkfirst=True)

    # Remove ENUM type
    site_enum.drop(op.get_bind(), checkfirst=True)