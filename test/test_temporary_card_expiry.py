"""Тести терміну дії тимчасових карток.

Поле «Czas pracy na tymczasowej karcie (godziny)» задає, скільки живе картка
гостя, видана тимчасовому працівникові. Фонова задача шукає картки, у яких
`last_used_at` старший за цей поріг, і ставить працівникові `expired`.

На проді не спрацьовувало жодного разу: створення працівника ставило лише
`used = True`, дата лишалась порожня, а умова `last_used_at IS NOT NULL`
такі картки відкидала. Відлік просто не стартував.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.main import oznacz_wygasle_karty
from models.db_employee import EmployeeDB
from models.db_guest import DBGuest
from routers.admin.api import create_temporary_employee

pytestmark = pytest.mark.asyncio


def _temu(godzin: float) -> datetime:
    # Zadanie porównuje czasy bez strefy, tak jak trzyma je kolumna.
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
    """Sedno usterki: bez tej daty karta nie wygasa nigdy."""
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
# Przejście zadania w tle
# ---------------------------------------------------------------------------
async def test_karta_po_terminie_gasi_pracownika(db_session):
    karta = await _karta(db_session, used=True, wydana=_temu(24))
    osoba = await _pracownik(db_session, karta.rfid)

    wynik = await oznacz_wygasle_karty(db_session, godzin=23)

    await db_session.refresh(osoba)
    assert osoba.expired is True
    assert wynik["wygaszeni"] == 1


async def test_karta_w_terminie_zostaje_aktywna(db_session):
    karta = await _karta(db_session, used=True, wydana=_temu(5))
    osoba = await _pracownik(db_session, karta.rfid)

    await oznacz_wygasle_karty(db_session, godzin=23)

    await db_session.refresh(osoba)
    assert osoba.expired is False


async def test_dluzszy_prog_przedluza_zycie_karty(db_session):
    """Próg bierze się z ustawień, więc ta sama karta zależy od liczby godzin."""
    karta = await _karta(db_session, used=True, wydana=_temu(30))
    osoba = await _pracownik(db_session, karta.rfid)

    await oznacz_wygasle_karty(db_session, godzin=72)
    await db_session.refresh(osoba)
    assert osoba.expired is False

    await oznacz_wygasle_karty(db_session, godzin=23)
    await db_session.refresh(osoba)
    assert osoba.expired is True


# ---------------------------------------------------------------------------
# Karty wydane dawniej, bez daty
# ---------------------------------------------------------------------------
async def test_wydanej_karcie_bez_daty_rusza_zegar(db_session):
    """Trzy karty na produkcji są wydane i nie mają daty. Lepiej policzyć je
    od tej chwili niż nigdy."""
    karta = await _karta(db_session, used=True, wydana=None)
    osoba = await _pracownik(db_session, karta.rfid)

    wynik = await oznacz_wygasle_karty(db_session, godzin=23)

    await db_session.refresh(karta)
    await db_session.refresh(osoba)
    assert karta.last_used_at is not None
    assert wynik["bez_daty"] == 1
    assert osoba.expired is False          # dopiero zaczyna biec


async def test_wolnej_karty_nie_ruszamy(db_session):
    """Karta nikomu nie wydana nie ma czego odliczać."""
    karta = await _karta(db_session, used=False, wydana=None)

    await oznacz_wygasle_karty(db_session, godzin=23)

    await db_session.refresh(karta)
    assert karta.last_used_at is None


async def test_drugie_przejscie_niczego_nie_psuje(db_session):
    """Zadanie chodzi co pół godziny — ma być obojętne na powtórzenia."""
    karta = await _karta(db_session, used=True, wydana=None)
    await _pracownik(db_session, karta.rfid)

    await oznacz_wygasle_karty(db_session, godzin=23)
    pierwsza_data = (await db_session.execute(
        select(DBGuest.last_used_at).where(DBGuest.id == karta.id)
    )).scalar_one()

    wynik = await oznacz_wygasle_karty(db_session, godzin=23)

    assert wynik["bez_daty"] == 0
    assert (await db_session.execute(
        select(DBGuest.last_used_at).where(DBGuest.id == karta.id)
    )).scalar_one() == pierwsza_data


async def test_zwykly_pracownik_bez_karty_goscia_nie_wygasa(db_session):
    """Stali pracownicy nie mają karty gościa i termin ich nie dotyczy."""
    osoba = await _pracownik(db_session, "11:22:33:44", wms_login="C-STALY")

    await oznacz_wygasle_karty(db_session, godzin=1)

    await db_session.refresh(osoba)
    assert osoba.expired is False
