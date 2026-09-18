"""Ślad sesji w logach.

Log dostępowy pokazuje tylko adres proksy, więc przy dwóch osobach naraz nie
wiadomo, czyj był 401. Tu każda linia ma login, skrót tokenu i powód.
"""
import logging
from datetime import timedelta

import pytest

from managers import session_log
from managers.auth_manager import auth_manager

pytestmark = pytest.mark.asyncio


async def test_token_nie_trafia_do_logu():
    token = auth_manager.create_access_token({"sub": "P-TVERDAH"}, timedelta(hours=1))

    skrot = session_log.tag(token)

    assert len(skrot) == 8
    assert skrot not in token


async def test_ten_sam_token_ma_ten_sam_skrot():
    """Po skrócie łączy się zdarzenia jednej sesji: login, ws_close, revoke."""
    token = auth_manager.create_access_token({"sub": "A"}, timedelta(hours=1))

    assert session_log.tag(token) == session_log.tag(token)


async def test_wlasciciel_znany_nawet_po_zdjeciu_sesji():
    """Po unieważnieniu sesji nie ma już w pamięci, a login dalej jest potrzebny."""
    token = auth_manager.create_access_token({"sub": "P-TVERDAH"}, timedelta(hours=1))
    auth_manager.remove_session(token)

    assert session_log.owner(token) == "P-TVERDAH"


async def test_linia_ma_prefiks_i_powod(caplog):
    token = auth_manager.create_access_token({"sub": "P-TVERDAH"}, timedelta(hours=1))

    with caplog.at_level(logging.INFO, logger="pinokio.session"):
        session_log.event("revoke", token, reason="ws_closed_no_reconnect", after_s=15)

    linia = caplog.records[-1].getMessage()
    assert linia.startswith("SESSION revoke ")
    assert "user=P-TVERDAH" in linia
    assert "reason=ws_closed_no_reconnect" in linia
    assert token not in linia


async def test_puste_pola_nie_smieca():
    import io

    bufor = io.StringIO()
    handler = logging.StreamHandler(bufor)
    log = logging.getLogger("pinokio.session")
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        session_log.event("login", None, user="x", esp=None)
    finally:
        log.removeHandler(handler)

    assert "esp=" not in bufor.getvalue()


async def test_blad_logu_nie_psuje_sesji(monkeypatch):
    """Log stoi w środku sprawdzania sesji — jego wyjątek nie może wylecieć."""
    def zepsuty(token):
        raise RuntimeError("boom")

    monkeypatch.setattr(session_log, "owner", zepsuty)

    session_log.event("reject", "cokolwiek", reason="x")      # bez wyjątku


async def test_sciezka_bez_obiektu_url():
    class Goly:
        pass

    assert session_log.path(Goly()) is None
