"""Usunięcie pracownika tymczasowego zwalnia jego kartę gościa.

Na produkcji GUEST17 była "zajęta", choć nikt jej nie miał: pracownika z tą
kartą usunięto, a flaga used została. Formularz tworzenia pracownika
tymczasowego nie pozwalał już jej wybrać, a w edycji gościa pole "used" jest
tylko do odczytu — karta wypadła z obiegu na dobre.
"""
import pytest
from sqlalchemy import select

from models.db_employee import EmployeeDB
from models.db_guest import DBGuest
from routers.admin.api import delete_employee

pytestmark = pytest.mark.asyncio


async def _karta(db, rfid="6D:EE:58:AD", used=True, name="GUEST17"):
    karta = DBGuest(name=name, rfid=rfid, used=used)
    db.add(karta)
    await db.commit()
    return karta


async def _pracownik(db, rfid):
    osoba = EmployeeDB(first_name="Test", last_name="Tymczasowy", company="TT",
                       wms_login="T-TYMCZASOWY", rfid=rfid)
    db.add(osoba)
    await db.commit()
    return osoba


async def test_usuniecie_zwalnia_karte_goscia(db_session):
    karta = await _karta(db_session)
    osoba = await _pracownik(db_session, karta.rfid)

    await delete_employee(employee_id=osoba.id, db=db_session, user=None)

    await db_session.refresh(karta)
    assert karta.used is False
    assert karta.last_used_at is None


async def test_zwolniona_karta_wraca_na_liste_wolnych(db_session):
    """To, co widzi formularz: lista z unused_only."""
    from routers.admin.api import get_guests

    karta = await _karta(db_session)
    osoba = await _pracownik(db_session, karta.rfid)
    assert karta.rfid not in [g.rfid for g in await get_guests(
        q=None, unused_only=True, db=db_session, user=None)]

    await delete_employee(employee_id=osoba.id, db=db_session, user=None)

    wolne = await get_guests(q=None, unused_only=True, db=db_session, user=None)
    assert karta.rfid in [g.rfid for g in wolne]


async def test_zwykly_pracownik_bez_karty_goscia_usuwa_sie_jak_dawniej(db_session):
    osoba = await _pracownik(db_session, "AA:BB:CC:DD")

    wynik = await delete_employee(employee_id=osoba.id, db=db_session, user=None)

    assert "usunięty" in wynik["message"]
    zostal = (await db_session.execute(
        select(EmployeeDB).where(EmployeeDB.id == osoba.id))).scalar_one_or_none()
    assert zostal is None


async def test_cudza_karta_zostaje_zajeta(db_session):
    """Zwalniamy tylko kartę usuwanej osoby, nie wszystkie."""
    moja = await _karta(db_session, rfid="11:11:11:11", name="GUEST1")
    cudza = await _karta(db_session, rfid="22:22:22:22", name="GUEST2")
    db_session.add(EmployeeDB(first_name="Inny", last_name="Ktos", company="TT",
                              wms_login="T-INNY", rfid=cudza.rfid))
    await db_session.commit()
    osoba = await _pracownik(db_session, moja.rfid)

    await delete_employee(employee_id=osoba.id, db=db_session, user=None)

    await db_session.refresh(cudza)
    assert cudza.used is True
