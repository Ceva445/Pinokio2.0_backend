"""Тести фільтрів історії реєстрацій (/admin/api/transactions).

Головне, що тут перевіряється: межі діапазону тепер із годиною, а не тільки з
датою, і при цьому вибір самої дати в полі «Do» досі означає весь той день.
"""
from datetime import datetime

import pytest

from models.db_device import DeviceDB, DeviceType
from models.db_employee import EmployeeDB
from models.db_transaction import TransactionDB, TransactionType
from routers.admin.admin_transactions import get_transactions

pytestmark = pytest.mark.asyncio


async def _call(db, **filters):
    params = {
        "page": 1, "employee_q": None, "device_q": None,
        "date_from": None, "date_to": None, "tx_type": None,
    }
    params.update(filters)
    return await get_transactions(db=db, user=None, **params)


@pytest.fixture
async def shift(db_session):
    """Одна зміна: видачі зранку, повернення після обіду."""
    anna = EmployeeDB(last_name="Nowak", first_name="Anna", rfid="r-anna",
                      company="Demo", wms_login="A-NOWAK", department="STOCK")
    db_session.add(anna)
    await db_session.commit()

    scanner = DeviceDB(name="TERM003", rfid="r-t3", serial_number="sn-t3",
                       type=DeviceType.scanner)
    db_session.add(scanner)
    await db_session.commit()

    moments = [
        (datetime(2026, 3, 10, 6, 5), TransactionType.registered),
        (datetime(2026, 3, 10, 9, 30), TransactionType.registered),
        (datetime(2026, 3, 10, 14, 45), TransactionType.unregistered),
        (datetime(2026, 3, 10, 22, 15), TransactionType.unregistered),
        (datetime(2026, 3, 11, 6, 0), TransactionType.registered),
    ]
    db_session.add_all([
        TransactionDB(timestamp=when, type=kind,
                      employee_id=anna.id, device_id=scanner.id)
        for when, kind in moments
    ])
    await db_session.commit()
    return {"anna": anna, "scanner": scanner}


# ---------------------------------------------------------------------------
# Година в межах діапазону
# ---------------------------------------------------------------------------
async def test_hour_narrows_the_range(db_session, shift):
    """Ранкова зміна — те, заради чого година й додавалась."""
    page = await _call(
        db_session,
        date_from=datetime(2026, 3, 10, 6, 0),
        date_to=datetime(2026, 3, 10, 12, 0),
    )
    assert page["total"] == 2


async def test_upper_bound_is_inclusive(db_session, shift):
    """Подія рівно на межі має потрапити у вибірку, а не випасти."""
    page = await _call(
        db_session,
        date_from=datetime(2026, 3, 10, 9, 30),
        date_to=datetime(2026, 3, 10, 9, 30),
    )
    assert page["total"] == 1


async def test_midnight_still_means_the_whole_day(db_session, shift):
    """Вибір самої дати (без години) не має обрізати день до 00:00 —
    інакше стара звичка «поставив дату» давала б порожній результат."""
    page = await _call(
        db_session,
        date_from=datetime(2026, 3, 10, 0, 0),
        date_to=datetime(2026, 3, 10, 0, 0),
    )
    assert page["total"] == 4


async def test_range_across_days(db_session, shift):
    page = await _call(
        db_session,
        date_from=datetime(2026, 3, 10, 20, 0),
        date_to=datetime(2026, 3, 11, 7, 0),
    )
    assert page["total"] == 2


# ---------------------------------------------------------------------------
# Тип операції
# ---------------------------------------------------------------------------
async def test_filter_by_operation_type(db_session, shift):
    registered = await _call(db_session, tx_type=TransactionType.registered)
    unregistered = await _call(db_session, tx_type=TransactionType.unregistered)

    assert registered["total"] == 3
    assert unregistered["total"] == 2
    assert all(t.type == TransactionType.registered for t in registered["items"])


async def test_type_and_hour_stack(db_session, shift):
    """Фільтри мають комбінуватись, а не заміняти один одного."""
    page = await _call(
        db_session,
        date_from=datetime(2026, 3, 10, 0, 0),
        date_to=datetime(2026, 3, 10, 0, 0),
        tx_type=TransactionType.unregistered,
    )
    assert page["total"] == 2


async def test_no_filters_returns_everything(db_session, shift):
    assert (await _call(db_session))["total"] == 5
