"""Тести історії змін пристрою (/admin/api/device-transactions).

Ендпоінт віддавав ORM-обʼєкти як є, а разом із ними — цілого користувача з
password_hash. Хеші паролів усіх, хто хоч раз редагував пристрій, отримував
кожен, хто відкривав екран «Historia zmian urządzenia».
"""
import json

import pytest

from models.db_device import DeviceDB, DeviceType
from models.db_user import UserDB, UserRole
from models.device_transaction import DeviceChangeTransaction
from routers.admin.admin_device_transactions import get_device_transactions

pytestmark = pytest.mark.asyncio

SECRET = "$pbkdf2-sha256$29000$tego-nie-wolno-wysylac"


async def _call(db, **filters):
    params = {
        "page": 1, "user_q": None, "device_q": None, "description_q": None,
        "date_from": None, "date_to": None,
    }
    params.update(filters)
    return await get_device_transactions(db=db, current_user=None, **params)


@pytest.fixture
async def history(db_session):
    admin = UserDB(first_name="Ola", last_name="Zima", username="ozima",
                   password_hash=SECRET, role=UserRole.admin)
    db_session.add(admin)
    await db_session.commit()

    device = DeviceDB(name="TERM003", rfid="r-t3", serial_number="sn-t3",
                      type=DeviceType.scanner)
    db_session.add(device)
    await db_session.commit()

    db_session.add(DeviceChangeTransaction(
        user_id=admin.id, device_id=device.id,
        description="device status: WORK -> SERWIS",
    ))
    await db_session.commit()

    return {"admin": admin, "device": device}


async def test_rows_do_not_carry_password_hashes(db_session, history):
    page = await _call(db_session)

    assert page["total"] == 1
    assert SECRET not in json.dumps(page, default=str)


async def test_row_still_holds_what_the_screen_draws(db_session, history):
    """Екран малює час, користувача, пристрій і опис — усе це має лишитись."""
    row = (await _call(db_session))["items"][0]

    assert row["user"] == {
        "id": history["admin"].id,
        "username": "ozima",
        "first_name": "Ola",
        "last_name": "Zima",
    }
    assert row["device"]["name"] == "TERM003"
    assert row["description"] == "device status: WORK -> SERWIS"
    assert row["timestamp"] is not None


# ---------------------------------------------------------------------------
# Пошук по опису
# ---------------------------------------------------------------------------
@pytest.fixture
async def wymiana(db_session, history):
    """Typowy wpis po wymianie sprzętu: stary numer seryjny zostaje wyłącznie
    w opisie, bo w samym urządzeniu stoi już nowy."""
    db_session.add_all([
        DeviceChangeTransaction(
            user_id=history["admin"].id, device_id=history["device"].id,
            description="2026-09-10 User: admin changed device serial number "
                        "XXRBJ231900180 to XXRBN245103077",
        ),
        DeviceChangeTransaction(
            user_id=history["admin"].id, device_id=history["device"].id,
            description="2026-09-10 User: admin changed device ip None to 10.6.251.4",
        ),
    ])
    await db_session.commit()
    return history


async def test_stary_numer_seryjny_da_sie_znalezc(db_session, wymiana):
    """Сенс задачі: маючи на руках старий SN із накладної, знайти пристрій."""
    page = await _call(db_session, description_q="XXRBJ231900180")

    assert page["total"] == 1
    assert "XXRBJ231900180" in page["items"][0]["description"]


async def test_szukanie_nie_patrzy_na_wielkosc_liter(db_session, wymiana):
    page = await _call(db_session, description_q="xxrbj231900180")

    assert page["total"] == 1


async def test_fragment_opisu_tez_dziala(db_session, wymiana):
    """Nie tylko numery — magazyn szuka też po tym, co się zmieniło."""
    page = await _call(db_session, description_q="ip None to 10.6.251.4")

    assert page["total"] == 1


async def test_brak_dopasowania_daje_pusto(db_session, wymiana):
    page = await _call(db_session, description_q="tego-tu-nie-ma")

    assert page["total"] == 0
    assert page["items"] == []


async def test_filtr_opisu_laczy_sie_z_pozostalymi(db_session, wymiana):
    """Filtry mają się składać, a nie zastępować."""
    razem = await _call(db_session, description_q="serial number", device_q="TERM003")
    obok = await _call(db_session, description_q="serial number", device_q="TERM999")

    assert razem["total"] == 1
    assert obok["total"] == 0


async def test_ekran_ma_pole_na_opis():
    """Sam endpoint nikomu nie pomoże, dopóki nie ma gdzie tego wpisać."""
    from pathlib import Path

    strona = Path("app/templates/admin/device_transactions/list.html").read_text(encoding="utf-8")

    assert 'id="deviceTransactionDescriptionSearch"' in strona
    assert 'params.append("description_q"' in strona
