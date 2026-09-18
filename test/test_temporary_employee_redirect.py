"""Po utworzeniu pracownika tymczasowego każdy wraca do swojego panelu.

Skrypt formularza jest wspólny dla admina i kierownika. Na sztywno wpisany
/admin/employees dawał kierownikowi 403, a strona błędu odsyła na logowanie —
wyglądało to jak wylogowanie tuż po udanym zapisie.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio

SZABLONY = Path("app/templates")
SKRYPT = Path("app/static/js/admin/temporary_employees.js")


def _szablon(panel: str) -> str:
    return (SZABLONY / panel / "temporary_employees" / "create.html").read_text(encoding="utf-8")


async def test_kierownik_wraca_do_swojego_dashboardu():
    assert 'data-after-create="/manager"' in _szablon("manager")


async def test_admin_wraca_do_listy_pracownikow():
    assert 'data-after-create="/admin/employees"' in _szablon("admin")


async def test_skrypt_bierze_adres_ze_strony():
    skrypt = SKRYPT.read_text(encoding="utf-8")

    assert "form.dataset.afterCreate" in skrypt
    # Stały adres zostaje tylko jako zapas, nie jako jedyna droga.
    assert 'window.location.href = "/admin/employees"' not in skrypt


async def test_kierownik_nie_trafia_na_strone_admina():
    """Sam cel przekierowania musi być stroną, którą kierownik może otworzyć."""
    import inspect

    from app.dependencies.admin import require_manager_or_admin
    from routers.manager.pages import manager_dashboard

    guard = inspect.signature(manager_dashboard).parameters["current_user"].default.dependency
    assert guard is require_manager_or_admin

