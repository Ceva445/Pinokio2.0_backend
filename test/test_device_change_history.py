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
        "page": 1, "user_q": None, "device_q": None,
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
