"""Karta zastępcza: pracownik zapomniał własnej i dostaje kartę gościa.

Sedno: employees.rfid zostaje nietknięte. Własna karta działa przez cały czas
pożyczki, a rejestracje z obu kart trafiają na ten sam rekord — inaczej jeden
człowiek rozpadłby się w statystyce na dwie osoby.
"""
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from models.db_borrowed_card import (
    POWOD_RECZNY,
    POWOD_TERMIN,
    POWOD_WLASNA_KARTA,
    BorrowedCardDB,
)
from models.db_device import DeviceType
from models.db_guest import DBGuest
from models.db_transaction import (
    TRANSACTION_SOURCE_BORROWED,
    TransactionDB,
    TransactionType,
)
from routers.admin.api import get_employees_with_card
from routers.admin.api_borrowed_cards import lista_aktywnych, wydaj_karte, zwolnij_karte
from routers.api import process_rfid
from services import borrowed_cards
from test.conftest import make_device, make_employee, make_guest

pytestmark = pytest.mark.asyncio

SUFFIX = "_v2"
KIEROWNIK = {"id": None, "username": "kier"}


def _status(manager):
    return manager.last(f"registration_status{SUFFIX}")


async def _ustaw_godziny(monkeypatch, godzin):
    """Termin pożyczki bierze się z konfiguracji administratora."""
    import routers.admin.api_borrowed_cards as modul

    async def _config(_db):
        return {"borrowed_card_duration_hours": godzin}

    monkeypatch.setattr(modul.config_manager, "get_config", _config)


async def _pozyczka(db, monkeypatch, employee, guest, godzin=12):
    await _ustaw_godziny(monkeypatch, godzin)
    return await wydaj_karte(
        payload={"employee_id": employee.id, "guest_id": guest.id},
        db=db, user=KIEROWNIK,
    )


# ---------------------------------------------------------------------------
# Lista pracowników do wyboru
# ---------------------------------------------------------------------------
async def test_lista_pokazuje_tylko_tych_z_karta(db_session):
    await make_employee(db_session, "AA:01", wms_login="Z-KARTA")
    bez = await make_employee(db_session, "AA:02", wms_login="BEZ-KARTY")
    bez.rfid = None
    await db_session.commit()

    lista = await get_employees_with_card(q=None, db=db_session, user=None)

    assert [p["wms_login"] for p in lista] == ["Z-KARTA"]


async def test_lista_pomija_zablokowanych(db_session):
    await make_employee(db_session, "AA:03", wms_login="ZABLOKOWANY", expired=True)

    assert await get_employees_with_card(q=None, db=db_session, user=None) == []


async def test_lista_szuka_po_loginie(db_session):
    """Szukajka patrzy też na login WMS, nie tylko na imię i nazwisko."""
    await make_employee(db_session, "AA:04", wms_login="ZZZ-PIERWSZY")
    await make_employee(db_session, "AA:05", wms_login="NOWAK")

    lista = await get_employees_with_card(q="nowak", db=db_session, user=None)

    assert [p["wms_login"] for p in lista] == ["NOWAK"]


# ---------------------------------------------------------------------------
# Wydanie karty
# ---------------------------------------------------------------------------
async def test_wydanie_nie_rusza_wlasnej_karty(db_session, monkeypatch):
    """Rdzeń całej funkcji: numer pracownika zostaje, jaki był."""
    osoba = await make_employee(db_session, "AA:10", wms_login="ZAPOMINALSKI")
    karta = await make_guest(db_session, "GO:01", "GUEST-1")

    await _pozyczka(db_session, monkeypatch, osoba, karta)
    await db_session.refresh(osoba)
    await db_session.refresh(karta)

    assert osoba.rfid == "AA:10"
    assert karta.used is True

    pozyczka = await borrowed_cards.aktywna_pracownika(db_session, osoba.id)
    assert pozyczka is not None
    assert pozyczka.rfid == "GO:01"
    assert pozyczka.returned_at is None


async def test_termin_bierze_sie_z_konfiguracji(db_session, monkeypatch):
    osoba = await make_employee(db_session, "AA:11", wms_login="TERMIN")
    karta = await make_guest(db_session, "GO:02", "GUEST-2")

    odp = await _pozyczka(db_session, monkeypatch, osoba, karta, godzin=5)

    pozyczka = await borrowed_cards.aktywna_pracownika(db_session, osoba.id)
    assert odp["hours"] == 5
    assert pozyczka.expires_at - pozyczka.issued_at == timedelta(hours=5)


async def test_bez_wlasnej_karty_nie_pozyczamy(db_session, monkeypatch):
    """Komu karty nigdy nie wydano, ten idzie przez pracownika tymczasowego."""
    osoba = await make_employee(db_session, "AA:12", wms_login="BEZ")
    osoba.rfid = None
    await db_session.commit()
    karta = await make_guest(db_session, "GO:03", "GUEST-3")

    with pytest.raises(HTTPException) as err:
        await _pozyczka(db_session, monkeypatch, osoba, karta)

    assert err.value.status_code == 400


async def test_zablokowanemu_nie_wydamy(db_session, monkeypatch):
    osoba = await make_employee(db_session, "AA:13", wms_login="BLOK", expired=True)
    karta = await make_guest(db_session, "GO:04", "GUEST-4")

    with pytest.raises(HTTPException) as err:
        await _pozyczka(db_session, monkeypatch, osoba, karta)

    assert err.value.status_code == 400


async def test_zajetej_karty_nie_wydamy(db_session, monkeypatch):
    osoba = await make_employee(db_session, "AA:14", wms_login="DRUGI")
    karta = await make_guest(db_session, "GO:05", "GUEST-5", used=True)

    with pytest.raises(HTTPException) as err:
        await _pozyczka(db_session, monkeypatch, osoba, karta)

    assert err.value.status_code == 400


async def test_jedna_pozyczka_na_pracownika(db_session, monkeypatch):
    osoba = await make_employee(db_session, "AA:15", wms_login="CHCIWY")
    pierwsza = await make_guest(db_session, "GO:06", "GUEST-6")
    druga = await make_guest(db_session, "GO:07", "GUEST-7")

    await _pozyczka(db_session, monkeypatch, osoba, pierwsza)

    with pytest.raises(HTTPException) as err:
        await _pozyczka(db_session, monkeypatch, osoba, druga)

    assert err.value.status_code == 400
    await db_session.refresh(druga)
    assert druga.used is False


# ---------------------------------------------------------------------------
# Czytnik
# ---------------------------------------------------------------------------
async def test_pozyczona_karta_otwiera_sesje_pracownika(
    db_session, monkeypatch, devices, manager, reg_manager, set_can_register
):
    set_can_register(True)
    osoba = await make_employee(db_session, "AA:20", wms_login="SESJA")
    karta = await make_guest(db_session, "GO:10", "GUEST-10")
    await _pozyczka(db_session, monkeypatch, osoba, karta)

    await process_rfid("d", {"rfid": "GO:10"}, devices, manager, db_session,
                       event_suffix=SUFFIX)

    sesja = reg_manager.get("d")
    assert sesja is not None
    assert sesja.employee.id == osoba.id
    assert sesja.borrowed is True
    assert "karta zastępcza" in _status(manager)["message"]


async def test_sprzet_idzie_na_pracownika_i_zostaje_slad(
    db_session, monkeypatch, devices, manager, reg_manager, set_can_register
):
    """Sprzęt zapisuje się na pracownika, a w historii widać, czym przyłożono."""
    set_can_register(True)
    osoba = await make_employee(db_session, "AA:21", wms_login="SPRZET")
    karta = await make_guest(db_session, "GO:11", "GUEST-11")
    skaner = await make_device(db_session, "DEV:1", "SKANER-1", DeviceType.scanner, "S-1")
    await _pozyczka(db_session, monkeypatch, osoba, karta)

    await process_rfid("d", {"rfid": "GO:11"}, devices, manager, db_session,
                       event_suffix=SUFFIX)
    await process_rfid("d", {"rfid": "DEV:1"}, devices, manager, db_session,
                       event_suffix=SUFFIX)

    await db_session.refresh(skaner)
    assert skaner.employee_id == osoba.id

    tx = (await db_session.execute(
        select(TransactionDB).where(TransactionDB.type == TransactionType.registered)
    )).scalars().all()
    assert len(tx) == 1
    assert tx[0].employee_id == osoba.id
    assert tx[0].source == TRANSACTION_SOURCE_BORROWED


async def test_wlasna_karta_dalej_dziala_i_nie_znaczy_historii(
    db_session, monkeypatch, devices, manager, reg_manager, set_can_register
):
    set_can_register(True)
    osoba = await make_employee(db_session, "AA:22", wms_login="OBIE")
    skaner = await make_device(db_session, "DEV:2", "SKANER-2", DeviceType.scanner, "S-2")

    await process_rfid("d", {"rfid": "AA:22"}, devices, manager, db_session,
                       event_suffix=SUFFIX)
    await process_rfid("d", {"rfid": "DEV:2"}, devices, manager, db_session,
                       event_suffix=SUFFIX)

    await db_session.refresh(skaner)
    tx = (await db_session.execute(select(TransactionDB))).scalars().all()
    assert skaner.employee_id == osoba.id
    assert tx[0].source is None


async def test_wlasna_karta_zamyka_pozyczke(
    db_session, monkeypatch, devices, manager, reg_manager, set_can_register
):
    """Karta się znalazła — zastępcza wraca do puli bez udziału kierownika."""
    set_can_register(True)
    osoba = await make_employee(db_session, "AA:23", wms_login="ZNALAZL")
    karta = await make_guest(db_session, "GO:12", "GUEST-12")
    await _pozyczka(db_session, monkeypatch, osoba, karta)

    await process_rfid("d", {"rfid": "AA:23"}, devices, manager, db_session,
                       event_suffix=SUFFIX)

    await db_session.refresh(karta)
    pozyczka = (await db_session.execute(select(BorrowedCardDB))).scalars().one()
    assert pozyczka.returned_at is not None
    assert pozyczka.returned_reason == POWOD_WLASNA_KARTA
    assert karta.used is False
    assert "zwrócona" in _status(manager)["message"]
    # Sesja startuje normalnie: to wciąż ten sam pracownik przy czytniku.
    assert reg_manager.get("d").employee.id == osoba.id


async def test_karta_po_terminie_nie_otwiera_sesji(
    db_session, monkeypatch, devices, manager, reg_manager, set_can_register
):
    set_can_register(True)
    osoba = await make_employee(db_session, "AA:24", wms_login="SPOZNIONY")
    karta = await make_guest(db_session, "GO:13", "GUEST-13")
    await _pozyczka(db_session, monkeypatch, osoba, karta)

    pozyczka = await borrowed_cards.aktywna_pracownika(db_session, osoba.id)
    pozyczka.expires_at = borrowed_cards.teraz_utc() - timedelta(minutes=1)
    await db_session.commit()

    await process_rfid("d", {"rfid": "GO:13"}, devices, manager, db_session,
                       event_suffix=SUFFIX)

    assert reg_manager.get("d") is None
    assert _status(manager)["status"] == "error"
    # Zadanie w tle chodzi co pół godziny — czytnik zwalnia kartę od razu.
    await db_session.refresh(karta)
    await db_session.refresh(pozyczka)
    assert karta.used is False
    assert pozyczka.returned_reason == POWOD_TERMIN


async def test_karta_po_zwrocie_jest_nieznana(
    db_session, monkeypatch, devices, manager, reg_manager, set_can_register
):
    set_can_register(True)
    osoba = await make_employee(db_session, "AA:25", wms_login="ODDAL")
    karta = await make_guest(db_session, "GO:14", "GUEST-14")
    await _pozyczka(db_session, monkeypatch, osoba, karta)
    pozyczka = await borrowed_cards.aktywna_pracownika(db_session, osoba.id)
    await borrowed_cards.zwroc(db_session, pozyczka, POWOD_RECZNY, guest=karta)

    await process_rfid("d", {"rfid": "GO:14"}, devices, manager, db_session,
                       event_suffix=SUFFIX)

    assert reg_manager.get("d") is None
    # Wolna karta gościa: czytnik mówi, co to za karta, i nic nie otwiera.
    assert _status(manager)["message"] == "To jest: GUEST-14"


# ---------------------------------------------------------------------------
# Zwalnianie
# ---------------------------------------------------------------------------
async def test_zadanie_w_tle_zwalnia_po_terminie(db_session, monkeypatch):
    osoba = await make_employee(db_session, "AA:30", wms_login="TLO")
    karta = await make_guest(db_session, "GO:20", "GUEST-20")
    await _pozyczka(db_session, monkeypatch, osoba, karta)

    pozyczka = await borrowed_cards.aktywna_pracownika(db_session, osoba.id)
    pozyczka.expires_at = borrowed_cards.teraz_utc() - timedelta(hours=1)
    await db_session.commit()

    assert await borrowed_cards.zwolnij_po_terminie(db_session) == 1

    await db_session.refresh(karta)
    await db_session.refresh(pozyczka)
    await db_session.refresh(osoba)
    assert karta.used is False
    assert pozyczka.returned_reason == POWOD_TERMIN
    # Własny numer pracownika przeżywa cały cykl bez zadrapania.
    assert osoba.rfid == "AA:30"


async def test_zadanie_kart_tymczasowych_nie_rusza_pozyczonej(db_session, monkeypatch):
    """Dwa zegary na jednej karcie: starsze zadanie ma ją omijać.

    Inaczej przy dłuższym terminie zastępczej karta zrobiłaby się wolna, choć
    wiersz pożyczki wciąż by trwał — i dałoby się ją wydać drugiej osobie.
    """
    from app.main import zdejmij_karty_po_terminie

    osoba = await make_employee(db_session, "AA:31", wms_login="OMIJANY")
    karta = await make_guest(db_session, "GO:21", "GUEST-21")
    await _pozyczka(db_session, monkeypatch, osoba, karta, godzin=48)

    pozyczka = await borrowed_cards.aktywna_pracownika(db_session, osoba.id)
    pozyczka.issued_at = borrowed_cards.teraz_utc() - timedelta(hours=30)
    karta.last_used_at = borrowed_cards.teraz_utc() - timedelta(hours=30)
    await db_session.commit()

    wynik = await zdejmij_karty_po_terminie(db_session, godzin=24)

    await db_session.refresh(karta)
    assert wynik["zdjete"] == 0
    assert karta.used is True


async def test_reczne_zwolnienie_oddaje_karte(db_session, monkeypatch):
    osoba = await make_employee(db_session, "AA:32", wms_login="RECZNY")
    karta = await make_guest(db_session, "GO:22", "GUEST-22")
    await _pozyczka(db_session, monkeypatch, osoba, karta)
    pozyczka = await borrowed_cards.aktywna_pracownika(db_session, osoba.id)

    await zwolnij_karte(pozyczka.id, db=db_session, user={"username": "admin"})

    await db_session.refresh(karta)
    await db_session.refresh(pozyczka)
    assert karta.used is False
    assert pozyczka.returned_reason == POWOD_RECZNY
    assert await lista_aktywnych(db=db_session, user=None) == []


async def test_dwa_razy_zwolnic_sie_nie_da(db_session, monkeypatch):
    osoba = await make_employee(db_session, "AA:33", wms_login="DWARAZY")
    karta = await make_guest(db_session, "GO:23", "GUEST-23")
    await _pozyczka(db_session, monkeypatch, osoba, karta)
    pozyczka = await borrowed_cards.aktywna_pracownika(db_session, osoba.id)
    await zwolnij_karte(pozyczka.id, db=db_session, user={"username": "admin"})

    with pytest.raises(HTTPException) as err:
        await zwolnij_karte(pozyczka.id, db=db_session, user={"username": "admin"})

    assert err.value.status_code == 400


async def test_lista_aktywnych_liczy_pozostaly_czas(db_session, monkeypatch):
    osoba = await make_employee(db_session, "AA:34", wms_login="LICZNIK")
    karta = await make_guest(db_session, "GO:24", "GUEST-24")
    await _pozyczka(db_session, monkeypatch, osoba, karta, godzin=12)

    lista = await lista_aktywnych(db=db_session, user=None)

    assert len(lista) == 1
    assert lista[0]["employee"]["wms_login"] == "LICZNIK"
    assert lista[0]["card"]["name"] == "GUEST-24"
    assert 11 * 3600 < lista[0]["seconds_left"] <= 12 * 3600


async def test_zwolniona_karta_wraca_na_liste_wolnych(db_session, monkeypatch):
    """Po zwrocie kartę można wydać komuś innemu."""
    pierwszy = await make_employee(db_session, "AA:35", wms_login="PIERWSZY")
    drugi = await make_employee(db_session, "AA:36", wms_login="DRUGI")
    karta = await make_guest(db_session, "GO:25", "GUEST-25")

    await _pozyczka(db_session, monkeypatch, pierwszy, karta)
    pozyczka = await borrowed_cards.aktywna_pracownika(db_session, pierwszy.id)
    await zwolnij_karte(pozyczka.id, db=db_session, user={"username": "admin"})

    await _pozyczka(db_session, monkeypatch, drugi, karta)

    wolne = (await db_session.execute(
        select(DBGuest).where(DBGuest.used.is_(False))
    )).scalars().all()
    assert wolne == []
    assert (await borrowed_cards.aktywna_pracownika(db_session, drugi.id)) is not None
