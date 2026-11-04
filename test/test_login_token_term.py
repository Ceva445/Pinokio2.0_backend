"""Termin sesji bierze się z panelu, a nie z liczby wpisanej w kodzie.

W „Konfiguracja systemu" stało pole „Czas wygaśnięcia tokenu dostępu", admin je
zapisywał, a /auth/login i tak wystawiał token na wszyte na sztywno 12 godzin.
Ustawienie było atrapą: pokazywało 30 minut, których nikt nigdy nie dostał.
"""
import pytest
from fastapi import Response

from managers.auth_manager import auth_manager
from models.db_user import UserDB, UserRole

HASLO = "haslo-testowe-123"


async def _admin(db, username="admin_term"):
    """Admin, bo tylko on loguje się bez wybierania czytnika ESP."""
    u = UserDB(
        first_name="Ala", last_name="Adminowa", username=username,
        password_hash=auth_manager.get_password_hash(HASLO),
        role=UserRole.admin, is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _zaloguj(db, monkeypatch, minuty, username="admin_term"):
    import routers.auth as auth_router

    async def _fake_config(_db):
        return {"access_token_expire_minutes": minuty}

    monkeypatch.setattr(auth_router.config_manager, "get_config", _fake_config)
    token = await auth_router.login_form(
        Response(), username=username, password=HASLO, device_id=None, db=db
    )
    payload = auth_manager.decode_token(token.access_token)
    assert payload is not None
    return payload["exp"] - payload["iat"]


@pytest.mark.asyncio
async def test_login_bierze_termin_z_konfiguracji(db_session, monkeypatch):
    await _admin(db_session)
    zycie = await _zaloguj(db_session, monkeypatch, 45)
    assert zycie == 45 * 60


@pytest.mark.asyncio
async def test_dwanascie_godzin_nie_jest_wszyte(db_session, monkeypatch):
    """Przy innym ustawieniu nie wraca stare timedelta(hours=12)."""
    await _admin(db_session)
    zycie = await _zaloguj(db_session, monkeypatch, 480)
    assert zycie == 480 * 60
    assert zycie != 12 * 3600


@pytest.mark.asyncio
async def test_bezsensowna_wartosc_wraca_do_domyslnej(db_session, monkeypatch):
    """Zero albo brak wpisu nie może dać tokenu, który wygasł przy wystawieniu."""
    import config as default_config

    await _admin(db_session)
    zycie = await _zaloguj(db_session, monkeypatch, 0)
    assert zycie == default_config.ACCESS_TOKEN_EXPIRE_MINUTES * 60


@pytest.mark.asyncio
async def test_domyslna_to_cala_zmiana():
    """Domyślny termin musi starczyć na zmianę — 30 minut było za krótko."""
    import config as default_config
    from managers.config_manager import config_manager

    assert default_config.ACCESS_TOKEN_EXPIRE_MINUTES == 720
    assert config_manager._get_default_config_dict()["access_token_expire_minutes"] == 720
