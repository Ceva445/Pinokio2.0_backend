"""Тести терміну дії тимчасових карток.

Поле «Czas pracy na tymczasowej karcie (godziny)» задає, скільки живе картка
гостя, видана тимчасовому працівникові. Після терміну фонова задача **знімає
картку**: працівникові лишається порожній RFID (отже, жодної реєстрації), а
картка повертається у список вільних і її можна видати іншому.

Сам працівник лишається в базі разом з історією та логіном WMS — його можна
прийняти вдруге через «Dodaj pracownika tymczasowego», замість заводити другий
запис із дописом у логіні.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.main import zdejmij_karty_po_terminie
from models.db_device import DeviceType
from models.db_employee import EmployeeDB
from models.db_guest import DBGuest
from routers.admin.api import create_temporary_employee

from test.conftest import make_device

pytestmark = pytest.mark.asyncio


def _temu(godzin: float) -> datetime:
    # Zadanie porownuje czasy bez strefy, tak jak trzyma je kolumna.
    return datetime.utcnow() - timedelta(hours=godzin)


async def _karta(db, name="GUEST01", rfid="AA:BB:CC:DD", used=False, wydana=None):
    karta = DBGuest(name=name, rfid=rfid, used=used, last_used_at=wydana)
    db.add(karta)
    await db.commit()
    return karta


async def _pracownik(db, rfid, wms_login="T-TYMCZASOWY"):
    osoba = EmployeeDB(first_name="Test", last_name="Tymczasowy", company="TT",
                       wms_login=wms_login, rfid=rfid)
    db.add(osoba)
    await db.commit()
    return osoba


# ---------------------------------------------------------------------------
# Wydanie karty uruchamia zegar
# ---------------------------------------------------------------------------
async def test_wydanie_karty_zapisuje_date(db_session):
    """Sedno pierwszej usterki: bez tej daty karta nie wygasa nigdy."""
    karta = await _karta(db_session)

    await create_temporary_employee(
        payload={"guest_id": karta.id, "first_name": "Jan", "last_name": "Nowak",
                 "company": "ACME", "wms_login": "T-NOWAK"},
        db=db_session, user=None,
    )

    await db_session.refresh(karta)
    assert karta.used is True
    assert karta.last_used_at is not None


# ---------------------------------------------------------------------------
# Przejscie zadania w tle
# ---------------------------------------------------------------------------
async def test_karta_po_terminie_wraca_do_puli(db_session):
    karta = await _karta(db_session, used=True, wydana=_temu(24))
    osoba = await _pracownik(db_session, karta.rfid)

    wynik = await zdejmij_karty_po_terminie(db_session, godzin=23)

    await db_session.refresh(karta)
    await db_session.refresh(osoba)
    assert osoba.rfid is None            # pracownik bez karty: zadnej rejestracji
    assert karta.used is False           # karta wolna, da sie wydac komus innemu
    assert karta.last_used_at is None
    assert wynik["zdjete"] == 1


async def test_pracownik_zostaje_w_bazie_z_historia(db_session):
    """Caly sens zmiany: rekord i login WMS maja przetrwac zdjecie karty."""
    karta = await _karta(db_session, used=True, wydana=_temu(24))
    osoba = await _pracownik(db_session, karta.rfid, wms_login="T-WRACAJACY")

    await zdejmij_karty_po_terminie(db_session, godzin=23)

    znaleziony = (await db_session.execute(
        select(EmployeeDB).where(EmployeeDB.id == osoba.id)
    )).scalar_one()
    assert znaleziony.wms_login == "T-WRACAJACY"


async def test_zdjecie_karty_nie_stawia_znacznika(db_session):
    """Znacznik expired to dzis wylacznie reczna blokada administratora.
    Stan "termin minal" widac po pustym RFID."""
    karta = await _karta(db_session, used=True, wydana=_temu(24))
    osoba = await _pracownik(db_session, karta.rfid)

    await zdejmij_karty_po_terminie(db_session, godzin=23)

    await db_session.refresh(osoba)
    assert osoba.expired is False


async def test_sprzet_zostaje_zapisany_na_pracownika(db_session):
    """Zdanie urzadzenia nie wymaga karty, wiec zabranie karty nie zwalnia
    sprzetu — inaczej zgubilibysmy, kto go trzyma."""
    karta = await _karta(db_session, used=True, wydana=_temu(24))
    osoba = await _pracownik(db_session, karta.rfid)
    sprzet = await make_device(db_session, "D-1", "Scan-1", DeviceType.scanner,
                               "S1", employee_id=osoba.id)

    await zdejmij_karty_po_terminie(db_session, godzin=23)

    await db_session.refresh(sprzet)
    assert sprzet.employee_id == osoba.id


async def test_karta_w_terminie_zostaje_u_pracownika(db_session):
    karta = await _karta(db_session, used=True, wydana=_temu(5))
    osoba = await _pracownik(db_session, karta.rfid)

    await zdejmij_karty_po_terminie(db_session, godzin=23)

    await db_session.refresh(karta)
    await db_session.refresh(osoba)
    assert osoba.rfid == karta.rfid
    assert karta.used is True


async def test_dluzszy_prog_przedluza_zycie_karty(db_session):
    """Prog bierze sie z ustawien, wiec ta sama karta zalezy od liczby godzin."""
    karta = await _karta(db_session, used=True, wydana=_temu(30))
    osoba = await _pracownik(db_session, karta.rfid)

    await zdejmij_karty_po_terminie(db_session, godzin=72)
    await db_session.refresh(osoba)
    assert osoba.rfid is not None

    await zdejmij_karty_po_terminie(db_session, godzin=23)
    await db_session.refresh(osoba)
    assert osoba.rfid is None


async def test_drugie_przejscie_niczego_nie_robi(db_session):
    """Zadanie chodzi co pol godziny — zdjeta karta ma byc poza zasiegiem."""
    karta = await _karta(db_session, used=True, wydana=_temu(24))
    await _pracownik(db_session, karta.rfid)

    await zdejmij_karty_po_terminie(db_session, godzin=23)
    wynik = await zdejmij_karty_po_terminie(db_session, godzin=23)

    assert wynik == {"bez_daty": 0, "zdjete": 0}


async def test_karta_bez_pracownika_tez_wraca(db_session):
    """Karta oznaczona jako wydana, ktorej nikt nie nosi (np. po recznej
    zmianie RFID) nie ma blokowac sie na zawsze."""
    karta = await _karta(db_session, used=True, wydana=_temu(24))

    wynik = await zdejmij_karty_po_terminie(db_session, godzin=23)

    await db_session.refresh(karta)
    assert karta.used is False
    assert wynik["zdjete"] == 1


# ---------------------------------------------------------------------------
# Karty wydane dawniej, bez daty
# ---------------------------------------------------------------------------
async def test_wydanej_karcie_bez_daty_rusza_zegar(db_session):
    """Karty wydane przed poprawka nie maja daty. Lepiej policzyc je od tej
    chwili niz nigdy."""
    karta = await _karta(db_session, used=True, wydana=None)
    osoba = await _pracownik(db_session, karta.rfid)

    wynik = await zdejmij_karty_po_terminie(db_session, godzin=23)

    await db_session.refresh(karta)
    await db_session.refresh(osoba)
    assert karta.last_used_at is not None
    assert wynik["bez_daty"] == 1
    assert osoba.rfid is not None          # dopiero zaczyna biec


async def test_wolnej_karty_nie_ruszamy(db_session):
    """Karta nikomu nie wydana nie ma czego odliczac."""
    karta = await _karta(db_session, used=False, wydana=None)

    await zdejmij_karty_po_terminie(db_session, godzin=23)

    await db_session.refresh(karta)
    assert karta.last_used_at is None


async def test_zwykly_pracownik_bez_karty_goscia_nietkniety(db_session):
    """Stali pracownicy nie maja karty goscia i termin ich nie dotyczy."""
    osoba = await _pracownik(db_session, "11:22:33:44", wms_login="C-STALY")

    await zdejmij_karty_po_terminie(db_session, godzin=1)

    await db_session.refresh(osoba)
    assert osoba.rfid == "11:22:33:44"
    assert osoba.expired is False


# ---------------------------------------------------------------------------
# Reczna blokada w panelu administratora
# ---------------------------------------------------------------------------
async def test_pole_expired_da_sie_kliknac():
    """Bylo na sztywno disabled — administrator nie mogl nic z nim zrobic."""
    from pathlib import Path

    strona = Path("app/templates/admin/employees/detail.html").read_text(encoding="utf-8")

    assert '<input type="checkbox" name="expired">' in strona
    assert 'name="expired" disabled' not in strona


async def test_reczna_blokada_zostawia_karte(db_session):
    """Blokada ma tylko wstrzymac rejestracje: karta i jej termin zostaja
    nietkniete, wiec odblokowanie nie przedluza niczego po cichu."""
    from routers.admin.api import update_employee

    karta = await _karta(db_session, used=True, wydana=_temu(2))
    osoba = await _pracownik(db_session, karta.rfid)

    await update_employee(employee_id=osoba.id, payload={"expired": True},
                          db=db_session, user=None)

    await db_session.refresh(osoba)
    await db_session.refresh(karta)
    assert osoba.expired is True
    assert osoba.rfid == karta.rfid
    assert karta.used is True
    assert karta.last_used_at < _temu(1)


async def test_odblokowanie_nie_przedluza_karty(db_session):
    from routers.admin.api import update_employee

    karta = await _karta(db_session, used=True, wydana=_temu(2))
    osoba = await _pracownik(db_session, karta.rfid)
    osoba.expired = True
    await db_session.commit()
    data_przed = karta.last_used_at

    await update_employee(employee_id=osoba.id, payload={"expired": False},
                          db=db_session, user=None)

    await db_session.refresh(karta)
    assert karta.last_used_at == data_przed


async def test_zwykla_edycja_nie_rusza_daty_karty(db_session):
    """Formularz przysyla tez rfid przy kazdym zapisie. Zmiana nazwiska nie ma
    prawa zwolnic karty ani przestawic jej daty."""
    from routers.admin.api import update_employee

    karta = await _karta(db_session, used=True, wydana=_temu(10))
    osoba = await _pracownik(db_session, karta.rfid)
    data_przed = karta.last_used_at

    await update_employee(employee_id=osoba.id,
                          payload={"last_name": "Inny", "rfid": karta.rfid},
                          db=db_session, user=None)

    await db_session.refresh(karta)
    await db_session.refresh(osoba)
    assert karta.last_used_at == data_przed
    assert karta.used is True
    assert osoba.rfid == karta.rfid


async def test_puste_rfid_z_formularza_zwalnia_karte(db_session):
    """Puste pole to brak karty, a nie pusty napis — drugi taki pracownik
    wpadlby na unikalny indeks."""
    from routers.admin.api import update_employee

    karta = await _karta(db_session, used=True, wydana=_temu(2))
    osoba = await _pracownik(db_session, karta.rfid)

    await update_employee(employee_id=osoba.id, payload={"rfid": "  "},
                          db=db_session, user=None)

    await db_session.refresh(karta)
    await db_session.refresh(osoba)
    assert osoba.rfid is None
    assert karta.used is False
    assert karta.last_used_at is None


async def test_dwoch_pracownikow_bez_karty(db_session):
    """Unikalny indeks na rfid musi zniesc wiele NULL-i."""
    pierwszy = await _pracownik(db_session, "AA:01", wms_login="T-PIERWSZY")
    drugi = await _pracownik(db_session, "AA:02", wms_login="T-DRUGI")

    pierwszy.rfid = None
    drugi.rfid = None
    await db_session.commit()

    bez_karty = (await db_session.execute(
        select(EmployeeDB).where(EmployeeDB.rfid.is_(None))
    )).scalars().all()
    assert len(bez_karty) == 2
