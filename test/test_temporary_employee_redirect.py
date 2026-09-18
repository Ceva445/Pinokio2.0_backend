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


# ---------------------------------------------------------------------------
# Zajęte karty gościa na liście wyboru
# ---------------------------------------------------------------------------
async def test_zajeta_karta_jest_widoczna_ale_niewybieralna():
    """Serwer i tak odrzuca użytą kartę ("Gość został już użyty"), ale dopiero
    po wypełnieniu całego formularza. Lista ma to powiedzieć od razu."""
    skrypt = SKRYPT.read_text(encoding="utf-8")

    assert "if (guest.used)" in skrypt
    assert "option.disabled = true" in skrypt
    assert 'option.className = "guest-option--used"' in skrypt


async def test_rfid_nie_zalezy_od_napisu_opcji():
    """Napis dostał dopisek " — zajęta"; RFID bierze się z atrybutu."""
    skrypt = SKRYPT.read_text(encoding="utf-8")

    assert "option.dataset.rfid" in skrypt
    assert "selectedOption.dataset.rfid" in skrypt


async def test_zajeta_karta_ma_wlasne_tlo():
    css = Path("app/static/css/admin.css").read_text(encoding="utf-8")

    assert "#guestSelect option.guest-option--used" in css
