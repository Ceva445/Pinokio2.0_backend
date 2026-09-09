"""Тести вкладки «Urządzenia» в панелі кierownika.

Дві речі, які тут важливі. Перша — пошук справді знаходить (у тому числі за
людиною, бо кierownik найчастіше питає «у кого цей сканер»). Друга, і головніша
— ця вкладка **тільки читає**: у роутері не має бути жодного способу створити,
змінити чи видалити пристрій, і жодного доступу до історії змін.
"""
import pytest
from fastapi import HTTPException

from models.db_device import DeviceDB, DeviceType
from models.db_device_status import DeviceStatusDB
from models.db_employee import EmployeeDB
from routers.manager import api_devices
from routers.manager.api_devices import get_device_statuses, get_devices

pytestmark = pytest.mark.asyncio


async def _call(db, **filters):
    params = {"q": None, "device_type": None, "status_ids": [], "assigned": None}
    params.update(filters)
    return await get_devices(db=db, user=None, **params)


@pytest.fixture
async def warehouse(db_session):
    """Дві людини, чотири пристрої: видані, вільний і несправний."""
    work_status = DeviceStatusDB(name="WORK")
    test_status = DeviceStatusDB(name="TESTY")
    db_session.add_all([work_status, test_status])
    await db_session.commit()

    anna = EmployeeDB(last_name="Nowak", first_name="Anna", rfid="r-anna",
                      company="Demo", wms_login="A-NOWAK", department="STOCK")
    bartek = EmployeeDB(last_name="Wójcik", first_name="Bartek", rfid="r-bartek",
                        company="Demo", wms_login="B-WOJCIK", department="ECOM")
    db_session.add_all([anna, bartek])
    await db_session.commit()

    db_session.add_all([
        DeviceDB(name="TERM003", rfid="rf-1", serial_number="sn-1",
                 type=DeviceType.scanner, employee_id=anna.id, status_id=work_status.id),
        DeviceDB(name="ZEBRA44", rfid="rf-2", serial_number="sn-2",
                 type=DeviceType.printer, employee_id=anna.id, status_id=work_status.id),
        DeviceDB(name="TERM004", rfid="rf-3", serial_number="sn-3",
                 type=DeviceType.scanner, employee_id=bartek.id, status_id=test_status.id),
        DeviceDB(name="TERM005", rfid="rf-4", serial_number="sn-4",
                 type=DeviceType.scanner, enabled=False),
    ])
    await db_session.commit()
    return {"anna": anna, "bartek": bartek, "work": work_status, "test": test_status}


# ---------------------------------------------------------------------------
# Головне: вкладка не дає нічого змінити
# ---------------------------------------------------------------------------
async def test_router_exposes_only_reads():
    """Жодного POST/PUT/PATCH/DELETE — інакше «без редагування» тримається
    лише на тому, що кнопки немає у шаблоні."""
    methods = set()
    for route in api_devices.router.routes:
        methods |= set(route.methods)

    assert methods <= {"GET", "HEAD"}, f"router pozwala na zapis: {methods}"


async def test_router_never_touches_change_history():
    """Історія змін пристрою — не для кierownika, тож моделі тут узагалі немає."""
    source = open(api_devices.__file__, encoding="utf-8").read()
    assert "DeviceChangeTransaction" not in source
    assert "device_change" not in source


# ---------------------------------------------------------------------------
# Пошук
# ---------------------------------------------------------------------------
async def test_lists_everything_without_filters(db_session, warehouse):
    devices = await _call(db_session)
    assert [d["name"] for d in devices] == ["TERM003", "TERM004", "TERM005", "ZEBRA44"]


async def test_search_by_device_name(db_session, warehouse):
    assert [d["name"] for d in await _call(db_session, q="ZEBRA")] == ["ZEBRA44"]


async def test_search_by_serial_and_rfid(db_session, warehouse):
    assert [d["name"] for d in await _call(db_session, q="sn-3")] == ["TERM004"]
    assert [d["name"] for d in await _call(db_session, q="rf-2")] == ["ZEBRA44"]


async def test_search_by_person(db_session, warehouse):
    """Найчастіше питання кierownika — «що на цій людині»."""
    assert [d["name"] for d in await _call(db_session, q="A-NOWAK")] == ["TERM003", "ZEBRA44"]
    assert [d["name"] for d in await _call(db_session, q="Wójcik")] == ["TERM004"]


async def test_search_is_case_insensitive(db_session, warehouse):
    assert [d["name"] for d in await _call(db_session, q="zebra")] == ["ZEBRA44"]


# ---------------------------------------------------------------------------
# Фільтри
# ---------------------------------------------------------------------------
async def test_filter_by_type(db_session, warehouse):
    scanners = await _call(db_session, device_type="scanner")
    printers = await _call(db_session, device_type="printer")

    assert len(scanners) == 3
    assert [d["name"] for d in printers] == ["ZEBRA44"]


async def test_unknown_type_is_rejected(db_session):
    with pytest.raises(HTTPException) as exc:
        await _call(db_session, device_type="router")
    assert exc.value.status_code == 400


async def test_filter_by_assignment(db_session, warehouse):
    wydane = await _call(db_session, assigned="assigned")
    wolne = await _call(db_session, assigned="unassigned")

    assert len(wydane) == 3
    assert [d["name"] for d in wolne] == ["TERM005"]


async def test_filter_by_status(db_session, warehouse):
    tests_only = await _call(db_session, status_ids=[warehouse["test"].id])
    assert [d["name"] for d in tests_only] == ["TERM004"]


async def test_filters_stack(db_session, warehouse):
    result = await _call(db_session, device_type="scanner", assigned="assigned",
                         status_ids=[warehouse["work"].id])
    assert [d["name"] for d in result] == ["TERM003"]


# ---------------------------------------------------------------------------
# Що саме віддаємо
# ---------------------------------------------------------------------------
async def test_row_says_who_holds_the_device(db_session, warehouse):
    rows = {d["name"]: d for d in await _call(db_session)}

    assert rows["TERM003"]["employee"]["wms_login"] == "A-NOWAK"
    assert rows["TERM003"]["employee"]["department"] == "STOCK"
    assert rows["TERM005"]["employee"] is None
    assert rows["TERM005"]["enabled"] is False


async def test_statuses_feed_the_filter(db_session, warehouse):
    statuses = await get_device_statuses(db=db_session, user=None)
    assert [s["name"] for s in statuses] == ["TESTY", "WORK"]
