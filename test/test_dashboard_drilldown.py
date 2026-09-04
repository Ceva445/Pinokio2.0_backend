"""Тести рознесення (drill-down) чисел дашборда.

Головна вимога: список, що розгортається під числом, має містити рівно ті
рядки, які це число порахувало. Тому кожен тест зіставляє drill-down із
самим get_dashboard, а не з константою.
"""
import pytest
from fastapi import HTTPException

from models.db_device import DeviceDB, DeviceType
from models.db_employee import EmployeeDB
from routers.admin.api import (
    get_dashboard,
    get_dashboard_devices,
    get_dashboard_employees,
)

pytestmark = pytest.mark.asyncio


async def _employee(db, wms_login, department, last_name="Kowalski"):
    e = EmployeeDB(
        last_name=last_name, first_name="Jan", rfid=f"rfid-{wms_login}",
        company="ACME", wms_login=wms_login, department=department,
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def _device(db, name, type_, employee_id=None, enabled=True):
    d = DeviceDB(
        name=name, rfid=f"rfid-{name}", serial_number=f"sn-{name}",
        type=type_, employee_id=employee_id, enabled=enabled,
    )
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return d


@pytest.fixture
async def warehouse(db_session):
    """Склад із усіма ситуаціями, які дашборд рахує окремо: працівник із
    кількома пристроями, зламаний пристрій, працівник без відділу і вільні
    пристрої, що нікому не видані."""
    anna = await _employee(db_session, "A-NOWAK", "STOCK", last_name="Nowak")
    bartek = await _employee(db_session, "B-WOJCIK", "STOCK", last_name="Wojcik")
    cezary = await _employee(db_session, "C-ZAJAC", None, last_name="Zajac")

    await _device(db_session, "SCAN-A1", DeviceType.scanner, anna.id)
    await _device(db_session, "PRINT-A2", DeviceType.printer, anna.id)
    await _device(db_session, "PRINT-B1", DeviceType.printer, bartek.id)
    await _device(db_session, "SCAN-B2", DeviceType.scanner, bartek.id, enabled=False)
    await _device(db_session, "SCAN-C1", DeviceType.scanner, cezary.id)
    await _device(db_session, "PRINT-FREE", DeviceType.printer)
    await _device(db_session, "PRINT-BROKEN", DeviceType.printer, enabled=False)

    return {"anna": anna, "bartek": bartek, "cezary": cezary}


async def _devices(db, **kwargs):
    """get_dashboard_devices із повним набором аргументів — при прямому виклику
    FastAPI не підставляє дефолти з Query()."""
    params = {"device_type": None, "enabled": None, "assigned": None, "department": None}
    params.update(kwargs)
    return await get_dashboard_devices(db=db, user=None, **params)


# ---------------------------------------------------------------------------
# Верхня таблиця: типи й доступність
# ---------------------------------------------------------------------------
async def test_type_counts_match_their_drilldown(db_session, warehouse):
    board = await get_dashboard(db=db_session, user=None)

    enabled_scanners = await _devices(db_session, device_type="scanner", enabled=True)
    disabled_scanners = await _devices(db_session, device_type="scanner", enabled=False)
    enabled_printers = await _devices(db_session, device_type="printer", enabled=True)
    disabled_printers = await _devices(db_session, device_type="printer", enabled=False)

    assert len(enabled_scanners) == board["devices"]["by_type"]["scanner"] == 2
    assert len(disabled_scanners) == board["devices"]["disabled_by_type"]["scanner"] == 1
    assert len(enabled_printers) == board["devices"]["by_type"]["printer"] == 3
    assert len(disabled_printers) == board["devices"]["disabled_by_type"]["printer"] == 1


async def test_totals_match_their_drilldown(db_session, warehouse):
    board = await get_dashboard(db=db_session, user=None)

    assert len(await _devices(db_session, enabled=True)) == board["devices"]["available"] == 5
    assert len(await _devices(db_session, enabled=False)) == board["devices"]["disabled"] == 2
    assert len(await _devices(db_session)) == 7


async def test_drilldown_says_who_holds_the_device(db_session, warehouse):
    """Сенс фічі: під числом видно не лише пристрій, а й його власника."""
    rows = {d["name"]: d for d in await _devices(db_session, device_type="scanner", enabled=True)}

    assert rows["SCAN-A1"]["employee"]["wms_login"] == "A-NOWAK"
    assert rows["SCAN-A1"]["employee"]["department"] == "STOCK"
    assert rows["SCAN-C1"]["employee"]["department"] is None


async def test_free_devices_have_no_holder(db_session, warehouse):
    rows = {d["name"]: d for d in await _devices(db_session, assigned=False)}

    assert set(rows) == {"PRINT-FREE", "PRINT-BROKEN"}
    assert all(d["employee"] is None for d in rows.values())


async def test_unknown_type_is_rejected(db_session):
    with pytest.raises(HTTPException) as exc:
        await _devices(db_session, device_type="router")
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Таблиця per dział
# ---------------------------------------------------------------------------
async def _department_row(db, name):
    board = await get_dashboard(db=db, user=None)
    return next(row for row in board["departments"] if row["department"] == name)


async def test_department_counts_match_their_drilldown(db_session, warehouse):
    row = await _department_row(db_session, "STOCK")
    scope = {"department": row["department_filter"], "enabled": True, "assigned": True}

    devices = await _devices(db_session, **scope)
    scanners = await _devices(db_session, device_type="scanner", **scope)
    printers = await _devices(db_session, device_type="printer", **scope)
    employees = await get_dashboard_employees(department=row["department_filter"], db=db_session, user=None)

    assert len(devices) == row["devices"] == 3
    assert len(scanners) == row["scanners"] == 1
    assert len(printers) == row["printers"] == 2
    assert len(employees) == row["employees"] == 2


async def test_employee_drilldown_lists_the_gear_each_person_has(db_session, warehouse):
    people = {e["wms_login"]: e for e in
              await get_dashboard_employees(department="STOCK", db=db_session, user=None)}

    assert [d["name"] for d in people["A-NOWAK"]["devices"]] == ["PRINT-A2", "SCAN-A1"]


async def test_employee_drilldown_keeps_withdrawn_gear(db_session, warehouse):
    """Несправний пристрій фізично лишається на працівнику, тому має бути в
    списку — але позначений, бо в число на дашборді він не входить."""
    people = {e["wms_login"]: e for e in
              await get_dashboard_employees(department="STOCK", db=db_session, user=None)}

    bartek = {d["name"]: d for d in people["B-WOJCIK"]["devices"]}
    assert sorted(bartek) == ["PRINT-B1", "SCAN-B2"]
    assert bartek["SCAN-B2"]["enabled"] is False
    assert bartek["PRINT-B1"]["enabled"] is True


async def test_row_without_department_is_reachable(db_session, warehouse):
    """Рядок "Brak" — це порожній параметр, а не літерал з таблиці."""
    row = await _department_row(db_session, "Brak")
    assert row["department_filter"] == ""

    devices = await _devices(db_session, department="", enabled=True, assigned=True)
    employees = await get_dashboard_employees(department="", db=db_session, user=None)

    assert [d["name"] for d in devices] == ["SCAN-C1"]
    assert [e["wms_login"] for e in employees] == ["C-ZAJAC"]
    assert len(devices) == row["devices"]
    assert len(employees) == row["employees"]


async def test_empty_department_does_not_pick_up_free_devices(db_session, warehouse):
    """Пристрій без власника теж дає NULL у колонці відділу після outerjoin —
    він не має потрапити до рядка "Brak"."""
    names = [d["name"] for d in await _devices(db_session, department="")]

    assert "PRINT-FREE" not in names
    assert "PRINT-BROKEN" not in names
