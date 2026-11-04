"""Set access_token_expire_minutes to the term login actually used (12 h)

Revision ID: a4c6e8b1d3f5
Revises: d1e3f5a7b9c2
Create Date: 2026-11-04 10:00:00.000000

Поле в «Konfiguracja systemu» зберігало 30 хвилин, а /auth/login видавав токен
на жорстко вшиті 12 годин і це значення не читав. Тепер логін читає конфіг, тож
залишені в БД 30 хвилин викидали б менеджерів посеред зміни — переставляємо
їх на 720 (12 годин), тобто на те, що система робила насправді. Рядки, де адмін
свідомо поставив щось інше, не чіпаємо.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a4c6e8b1d3f5'
down_revision: Union[str, Sequence[str], None] = 'd1e3f5a7b9c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "UPDATE system_config SET access_token_expire_minutes = 720 "
        "WHERE access_token_expire_minutes = 30"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "UPDATE system_config SET access_token_expire_minutes = 30 "
        "WHERE access_token_expire_minutes = 720"
    )
