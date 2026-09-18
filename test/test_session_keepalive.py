"""Przejście z monitora do panelu nie jest zamknięciem karty.

Gniazdo /ws mają tylko monitory. Kierowniczka szła z /monitor2 do "Historia
rejestracji" w tej samej karcie, gniazdo się rwało, a po 15 s serwer uznawał,
że zamknęła przeglądarkę — i unieważniał sesję. Pierwsze zapytanie po tych
15 s (filtr TERM116) kończyło się 401 i ekranem logowania.

Teraz liczy się to, czy człowiek dalej pracuje: zapytania, które sam wywołał,
trzymają sesję i kasują licznik bezczynności. Automaty — nie.
"""
import inspect
from datetime import datetime, timedelta, timezone

import pytest

import app.main as main
from app.main import (
    AUTOMATIC_PATHS,
    NAVIGATION_OVERLAP_SECONDS,
    note_user_request,
    still_working_after_ws_close,
)

pytestmark = pytest.mark.asyncio

TOKEN = "token-kierowniczki"


@pytest.fixture(autouse=True)
def czysta_pamiec():
    for stan in (main.token_last_user_request, main.esp_watchers, main.esp_last_activity):
        stan.clear()
    yield
    for stan in (main.token_last_user_request, main.esp_watchers, main.esp_last_activity):
        stan.clear()


def _teraz():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Co się liczy jako praca człowieka
# ---------------------------------------------------------------------------
async def test_zapytanie_czlowieka_jest_zapamietane():
    note_user_request(TOKEN, "/manager/api/transactions")

    assert TOKEN in main.token_last_user_request


async def test_automatyczne_sprawdzanie_sesji_sie_nie_liczy():
    """base.html co 5 s pyta /auth/me. Gdyby to się liczyło, zapomniana karta
    trzymałaby sesję i czytnik bez końca."""
    assert "/auth/me" in AUTOMATIC_PATHS

    note_user_request(TOKEN, "/auth/me")

    assert TOKEN not in main.token_last_user_request


async def test_praca_w_panelu_kasuje_licznik_bezczynnosci_jej_czytnika():
    main.esp_watchers["E-2"] = {"token": TOKEN, "username": "P-TVERDAH"}
    main.esp_last_activity["E-2"] = _teraz() - timedelta(minutes=14)

    note_user_request(TOKEN, "/manager/transactions")

    assert _teraz() - main.esp_last_activity["E-2"] < timedelta(seconds=2)


async def test_cudza_praca_nie_trzyma_mojego_czytnika():
    stara = _teraz() - timedelta(minutes=14)
    main.esp_watchers["E-2"] = {"token": TOKEN}
    main.esp_last_activity["E-2"] = stara

    note_user_request("token-kogos-innego", "/manager/transactions")

    assert main.esp_last_activity["E-2"] == stara


# ---------------------------------------------------------------------------
# Decyzja po zerwaniu gniazda
# ---------------------------------------------------------------------------
async def test_pracuje_w_panelu_po_zerwaniu_zostaje():
    zerwane = _teraz()
    main.token_last_user_request[TOKEN] = zerwane + timedelta(seconds=9)   # filtr TERM116

    assert still_working_after_ws_close(TOKEN, zerwane) is True


async def test_nowa_strona_przed_zerwaniem_tez_sie_liczy():
    """Przeglądarka najpierw pyta o nową stronę, potem zamyka starą — więc
    GET /manager/ bywa o ułamek sekundy wcześniejszy niż zerwanie gniazda."""
    zerwane = _teraz()
    main.token_last_user_request[TOKEN] = zerwane - timedelta(seconds=1)

    assert still_working_after_ws_close(TOKEN, zerwane) is True


async def test_zamknieta_karta_bez_zapytan_odchodzi():
    assert still_working_after_ws_close(TOKEN, _teraz()) is False


async def test_stara_aktywnosc_nie_ratuje_zamknietej_karty():
    zerwane = _teraz()
    main.token_last_user_request[TOKEN] = zerwane - timedelta(
        seconds=NAVIGATION_OVERLAP_SECONDS + 30)

    assert still_working_after_ws_close(TOKEN, zerwane) is False


async def test_uniewazniony_token_niczego_nie_pamieta():
    main.token_last_user_request[TOKEN] = _teraz()

    main.release_esp_for_token(TOKEN)

    assert TOKEN not in main.token_last_user_request


# ---------------------------------------------------------------------------
# Podpięcie
# ---------------------------------------------------------------------------
async def test_kazde_zapytanie_z_sesja_przechodzi_przez_notatke():
    from routers import auth

    zrodlo = inspect.getsource(auth.get_current_user)

    # Obie drogi sukcesu: z pamięci i z bazy.
    assert zrodlo.count("_note_user_request(token, request)") == 2


async def test_gniazdo_pyta_o_prace_zanim_uniewazni():
    from routers import websocket

    zrodlo = inspect.getsource(websocket.websocket_endpoint)
    decyzja = zrodlo.index("still_working_after_ws_close(t, closed_at)")
    uniewaznienie = zrodlo.index("revoked_tokens.add(t)")

    assert decyzja < uniewaznienie


class _Url:
    def __init__(self, path):
        self.path = path


class _Request:
    def __init__(self, token, path):
        self.cookies = {"access_token": token}
        self.url = _Url(path)


async def _kierowniczka(db_session):
    from managers.auth_manager import auth_manager
    from models.db_user import UserDB, UserRole

    db_session.add(UserDB(first_name="Hanna", last_name="Tverda", username="P-TVERDAH",
                          password_hash="x", role=UserRole.manager))
    await db_session.commit()
    auth_manager.active_sessions.clear()
    return auth_manager.create_access_token({"sub": "P-TVERDAH"}, timedelta(hours=1))


async def test_filtr_w_historii_trzyma_sesje(db_session):
    from routers.auth import get_current_user

    token = await _kierowniczka(db_session)
    await get_current_user()(request=_Request(token, "/manager/api/transactions"),
                             token=None, db=db_session)

    assert token in main.token_last_user_request


async def test_sprawdzanie_sesji_co_5s_nie_trzyma_sesji(db_session):
    from routers.auth import get_current_user

    token = await _kierowniczka(db_session)
    await get_current_user()(request=_Request(token, "/auth/me"), token=None, db=db_session)

    assert token not in main.token_last_user_request
