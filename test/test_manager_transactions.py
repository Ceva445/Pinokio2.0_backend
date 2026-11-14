"""Historia rejestracji u kierownika (/manager/api/transactions).

Ten ekran ma własną, starszą implementację niż ekran administratora i przez to
oddawał wiersze wprost z ORM — razem z całym managerem i jego password_hash.
Teraz liczy je ta sama funkcja co u administratora, więc i kształt wiersza,
i filtr karty zastępczej są wspólne.
"""
import json
from datetime import datetime

import pytest

from models.db_device import DeviceDB, DeviceType
from models.db_employee import EmployeeDB
from models.db_transaction import (
    TRANSACTION_SOURCE_BORROWED,
    TransactionDB,
    TransactionType,
)
from models.db_user import UserDB, UserRole
from routers.manager.api_transactions import get_transactions

pytestmark = pytest.mark.asyncio


async def _call(db, **filtry):
    params = {
        "page": 1, "employee_q": None, "device_q": None,
        "date_from": None, "date_to": None, "tx_type": None, "source": None,
    }
    params.update(filtry)
    return await get_transactions(db=db, user=None, **params)


@pytest.fixture
async def zmiana(db_session):
    osoba = EmployeeDB(last_name="Nowak", first_name="Anna", rfid="r-anna",
                       company="Demo", wms_login="A-NOWAK")
    kierownik = UserDB(first_name="Viktoriia", last_name="Riabiik",
                       username="P-RIABIIKV", password_hash="$pbkdf2$tajne-haslo",
                       role=UserRole.manager)
    db_session.add_all([osoba, kierownik])
    await db_session.commit()

    urzadzenie = DeviceDB(name="TERM003", rfid="r-t3", serial_number="sn-t3",
                          type=DeviceType.scanner)
    db_session.add(urzadzenie)
    await db_session.commit()

    db_session.add_all([
        TransactionDB(timestamp=datetime(2026, 3, 10, 6, 5),
                      type=TransactionType.registered, employee_id=osoba.id,
                      device_id=urzadzenie.id, manager_id=kierownik.id,
                      source=TRANSACTION_SOURCE_BORROWED),
        TransactionDB(timestamp=datetime(2026, 3, 10, 9, 30),
                      type=TransactionType.registered, employee_id=osoba.id,
                      device_id=urzadzenie.id, manager_id=kierownik.id),
    ])
    await db_session.commit()
    return {"osoba": osoba, "kierownik": kierownik}


async def test_wiersz_nie_niesie_hasla(db_session, zmiana):
    strona = await _call(db_session)

    assert "tajne-haslo" not in json.dumps(strona, default=str)
    podpisane = [t for t in strona["items"] if t["manager"]]
    assert podpisane and set(podpisane[0]["manager"]) == {
        "id", "username", "first_name", "last_name"
    }


async def test_filtr_karty_zastepczej(db_session, zmiana):
    zastepcza = await _call(db_session, source="borrowed")
    wlasna = await _call(db_session, source="own")

    assert zastepcza["total"] == 1
    assert zastepcza["items"][0]["source"] == TRANSACTION_SOURCE_BORROWED
    assert wlasna["total"] == 1
    assert wlasna["items"][0]["source"] is None


async def test_bez_filtra_widac_wszystko(db_session, zmiana):
    assert (await _call(db_session))["total"] == 2
