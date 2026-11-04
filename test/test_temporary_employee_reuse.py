"""Тести повторного прийняття працівника, якому зняли картку.

Після терміну картка відчіпляється від працівника, а сам запис лишається.
Форма «Dodaj pracownika tymczasowego» має вміти взяти цей запис і видати йому
нову картку — тоді історія й логін WMS не дробляться між двома записами.
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from models.db_employee import EmployeeDB
from models.db_guest import DBGuest
from routers.admin.api import create_temporary_employee, get_employees_without_card

pytestmark = pytest.mark.asyncio


async def _karta(db, name, rfid, used=False):
    karta = DBGuest(name=name, rfid=rfid, used=used)
    db.add(karta)
    await db.commit()
    await db.refresh(karta)
    return karta


async def _bez_karty(db, wms_login="T-WOLNY", expired=False):
    osoba = EmployeeDB(first_name="Ola", last_name="Bezkarty", company="TT",
                       wms_login=wms_login, rfid=None, expired=expired)
    db.add(osoba)
    await db.commit()
    await db.refresh(osoba)
    return osoba


# ---------------------------------------------------------------------------
# Pula do ponownego zatrudnienia
# ---------------------------------------------------------------------------
async def test_lista_pokazuje_tylko_bez_karty(db_session):
    await _bez_karty(db_session, wms_login="T-WOLNY1")
    z_karta = EmployeeDB(first_name="Jan", last_name="Zkarta", company="TT",
                         wms_login="T-ZKARTA", rfid="AA:01")
    db_session.add(z_karta)
    await db_session.commit()

    lista = await get_employees_without_card(db=db_session, user=None)

    assert [p["wms_login"] for p in lista] == ["T-WOLNY1"]


async def test_lista_pomija_zablokowanych(db_session):
    """Blokade zdejmuje administrator w edycji pracownika, a nie kierownik
    przez wydanie nowej karty."""
    await _bez_karty(db_session, wms_login="T-ZABLOKOWANY", expired=True)

    lista = await get_employees_without_card(db=db_session, user=None)

    assert lista == []


# ---------------------------------------------------------------------------
# Ponowne wydanie karty
# ---------------------------------------------------------------------------
async def test_ponowne_wydanie_nie_tworzy_dubla(db_session):
    osoba = await _bez_karty(db_session, wms_login="T-WRACA")
    karta = await _karta(db_session, "GUEST05", "BB:05")

    wynik = await create_temporary_employee(
        payload={"guest_id": karta.id, "employee_id": osoba.id},
        db=db_session, user=None,
    )

    await db_session.refresh(osoba)
    await db_session.refresh(karta)
    assert wynik["employee"].id == osoba.id
    assert osoba.rfid == "BB:05"
    assert karta.used is True
    assert karta.last_used_at is not None

    wszyscy = (await db_session.execute(select(EmployeeDB))).scalars().all()
    assert len(wszyscy) == 1


async def test_ponowne_wydanie_nie_rusza_danych(db_session):
    """Pola w formularzu sa tylko do wgladu, wiec to, co przyjdzie w payloadzie,
    nie ma prawa nadpisac kadr."""
    osoba = await _bez_karty(db_session, wms_login="T-WRACA2")
    karta = await _karta(db_session, "GUEST06", "BB:06")

    await create_temporary_employee(
        payload={"guest_id": karta.id, "employee_id": osoba.id,
                 "first_name": "Podmieniony", "company": "OBCA"},
        db=db_session, user=None,
    )

    await db_session.refresh(osoba)
    assert osoba.first_name == "Ola"
    assert osoba.company == "TT"


async def test_ponowne_wydanie_nie_wymaga_danych_osobowych(db_session):
    """Bez employee_id formularz musi podac imie, nazwisko i firme; z nim —
    biora sie z bazy."""
    osoba = await _bez_karty(db_session, wms_login="T-WRACA3")
    karta = await _karta(db_session, "GUEST07", "BB:07")

    wynik = await create_temporary_employee(
        payload={"guest_id": karta.id, "employee_id": osoba.id},
        db=db_session, user=None,
    )

    assert "ponownie" in wynik["message"]


async def test_pracownik_z_karta_odrzucony(db_session):
    osoba = EmployeeDB(first_name="Jan", last_name="Zkarta", company="TT",
                       wms_login="T-MAKARTE", rfid="AA:09")
    db_session.add(osoba)
    await db_session.commit()
    karta = await _karta(db_session, "GUEST08", "BB:08")

    with pytest.raises(HTTPException) as blad:
        await create_temporary_employee(
            payload={"guest_id": karta.id, "employee_id": osoba.id},
            db=db_session, user=None,
        )

    assert blad.value.status_code == 400
    assert "ma już kartę" in blad.value.detail


async def test_zablokowanego_nie_da_sie_zatrudnic(db_session):
    osoba = await _bez_karty(db_session, wms_login="T-ZABL2", expired=True)
    karta = await _karta(db_session, "GUEST09", "BB:09")

    with pytest.raises(HTTPException) as blad:
        await create_temporary_employee(
            payload={"guest_id": karta.id, "employee_id": osoba.id},
            db=db_session, user=None,
        )

    assert blad.value.status_code == 400
    assert "zablokowany" in blad.value.detail

    await db_session.refresh(karta)
    assert karta.used is False


async def test_zajeta_karta_odrzucona(db_session):
    osoba = await _bez_karty(db_session, wms_login="T-WRACA4")
    karta = await _karta(db_session, "GUEST10", "BB:10", used=True)

    with pytest.raises(HTTPException) as blad:
        await create_temporary_employee(
            payload={"guest_id": karta.id, "employee_id": osoba.id},
            db=db_session, user=None,
        )

    assert blad.value.status_code == 400


async def test_nieznany_pracownik_to_404(db_session):
    karta = await _karta(db_session, "GUEST11", "BB:11")

    with pytest.raises(HTTPException) as blad:
        await create_temporary_employee(
            payload={"guest_id": karta.id, "employee_id": 9999},
            db=db_session, user=None,
        )

    assert blad.value.status_code == 404


async def test_formularz_ma_pole_wyboru_pracownika():
    """Oba ekrany — administratora i kierownika — korzystaja z jednego JS."""
    from pathlib import Path

    for strona in ("app/templates/admin/temporary_employees/create.html",
                   "app/templates/manager/temporary_employees/create.html"):
        tresc = Path(strona).read_text(encoding="utf-8")
        assert 'id="reuseEmployeeSelect"' in tresc, strona

    skrypt = Path("app/static/js/admin/temporary_employees.js").read_text(encoding="utf-8")
    assert "/admin/api/employees/without-card" in skrypt
