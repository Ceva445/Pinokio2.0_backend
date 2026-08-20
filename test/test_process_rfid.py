"""Тести бізнес-логіки нового ендпоінта (process_rfid) на реальній sqlite.

process_rfid — спільна логіка для POST /api/data2/{id} і WS /ws/device/{id}
(обидва → /monitor2). Старий /data сюди не входить.

Групи відповідають узгодженим тесткейсам T0..T4.
"""
import pytest
from sqlalchemy import select, func

from routers.api import process_rfid
from models.db_device import DeviceType
from models.db_transaction import TransactionDB, TransactionType

from test.conftest import make_employee, make_device, make_guest

SUFFIX = "_v2"


async def _tx_count(db, type_=None):
    stmt = select(func.count()).select_from(TransactionDB)
    if type_ is not None:
        stmt = stmt.where(TransactionDB.type == type_)
    return (await db.execute(stmt)).scalar_one()


def _status(manager):
    return manager.last(f"registration_status{SUFFIX}")


# ===========================================================================
# ГРУПА 0 — вхід
# ===========================================================================
async def test_T0_1_no_rfid_no_status_broadcast(db_session, devices, manager, reg_manager, set_can_register):
    set_can_register(True)
    res = await process_rfid("dev-1", {"temp": 21}, devices, manager, db_session, event_suffix=SUFFIX)

    assert res == {"status": "info", "message": None}
    # статус НЕ транслюється, але дані пристрою — так
    assert _status(manager) is None
    assert manager.last(f"esp32_data{SUFFIX}") is not None
    assert manager.device_list_calls == 1


# ===========================================================================
# ГРУПА 1 — режим довідки (can_register = False)
# ===========================================================================
async def test_T1_1_unknown_rfid(db_session, devices, manager, reg_manager, set_can_register):
    set_can_register(False)
    await process_rfid("d", {"rfid": "NOPE"}, devices, manager, db_session, event_suffix=SUFFIX)
    p = _status(manager)
    assert p["status"] == "error"
    assert p["message"] == "Nieznany RFID"


async def test_T1_2_guest_unused_found(db_session, devices, manager, reg_manager, set_can_register):
    set_can_register(False)
    await make_guest(db_session, "G1", "Gość Jan", used=False)
    await process_rfid("d", {"rfid": "G1"}, devices, manager, db_session, event_suffix=SUFFIX)
    p = _status(manager)
    assert p["status"] == "success"
    assert p["message"] == "To jest: Gość Jan"


async def test_T1_2b_guest_used_is_filtered_out_after_fix(db_session, devices, manager, reg_manager, set_can_register):
    """Фікс and→кома: гість з used=True НЕ повертається → 'Nieznany RFID'."""
    set_can_register(False)
    await make_guest(db_session, "G2", "Gość Stary", used=True)
    await process_rfid("d", {"rfid": "G2"}, devices, manager, db_session, event_suffix=SUFFIX)
    p = _status(manager)
    assert p["status"] == "error"
    assert p["message"] == "Nieznany RFID"


async def test_T1_3_employee_info_lists_devices(db_session, devices, manager, reg_manager, set_can_register):
    set_can_register(False)
    e = await make_employee(db_session, "EMP1", wms_login="jan")
    await make_device(db_session, "DEV1", "Scan-1", DeviceType.scanner, "S1", employee_id=e.id)
    await process_rfid("d", {"rfid": "EMP1"}, devices, manager, db_session, event_suffix=SUFFIX)
    p = _status(manager)
    assert p["status"] == "info"
    assert "Pracownik jan posiada" in p["message"]
    assert "scanner: Scan-1" in p["message"]


async def test_T1_4_employee_expired_warning(db_session, devices, manager, reg_manager, set_can_register):
    set_can_register(False)
    await make_employee(db_session, "EMP2", wms_login="ola", expired=True)
    await process_rfid("d", {"rfid": "EMP2"}, devices, manager, db_session, event_suffix=SUFFIX)
    p = _status(manager)
    assert p["status"] == "warning"
    assert "wygasła" in p["message"]


async def test_T1_5_device_unassigned_info(db_session, devices, manager, reg_manager, set_can_register):
    set_can_register(False)
    await make_device(db_session, "DEV2", "Scan-2", DeviceType.scanner, "S2", employee_id=None)
    await process_rfid("d", {"rfid": "DEV2"}, devices, manager, db_session, event_suffix=SUFFIX)
    p = _status(manager)
    assert p["status"] == "info"
    assert "nie jest przypisany do nikogo" in p["message"]


async def test_T1_6_device_assigned_shows_owner(db_session, devices, manager, reg_manager, set_can_register):
    set_can_register(False)
    e = await make_employee(db_session, "EMP3", wms_login="bob")
    await make_device(db_session, "DEV3", "Print-3", DeviceType.printer, "P3", employee_id=e.id)
    await process_rfid("d", {"rfid": "DEV3"}, devices, manager, db_session, event_suffix=SUFFIX)
    p = _status(manager)
    assert p["status"] == "info"
    assert "należy do bob" in p["message"]
    assert "Brak uprawnień" in p["message"]


# ===========================================================================
# ГРУПА 2 — режим реєстрації (can_register = True)
# ===========================================================================
async def test_T2_1_employee_starts_session(db_session, devices, manager, reg_manager, set_can_register):
    set_can_register(True)
    e = await make_employee(db_session, "EMP4", wms_login="ann")
    await process_rfid("dev-reg", {"rfid": "EMP4"}, devices, manager, db_session, event_suffix=SUFFIX)
    p = _status(manager)
    assert p["status"] == "success"
    assert "Pracownik ann aktywny" in p["message"]
    # сесія стартувала
    session = reg_manager.get("dev-reg")
    assert session is not None
    assert session.employee.id == e.id
    # T3.1 — у payload є таймер
    assert p["session"] is not None
    assert p["session"]["timeout_seconds"] > 0


async def test_T2_2_employee_expired_still_starts_session_but_warns(db_session, devices, manager, reg_manager, set_can_register):
    set_can_register(True)
    await make_employee(db_session, "EMP5", wms_login="ola2", expired=True)
    await process_rfid("dev-x", {"rfid": "EMP5"}, devices, manager, db_session, event_suffix=SUFFIX)
    p = _status(manager)
    assert p["status"] == "warning"
    assert "wygasła" in p["message"]
    assert reg_manager.get("dev-x") is not None  # сесія все одно стартувала


async def test_T2_3_device_no_session_unassigned_error(db_session, devices, manager, reg_manager, set_can_register):
    set_can_register(True)
    await make_device(db_session, "DEV6", "Scan-6", DeviceType.scanner, "S6", employee_id=None)
    await process_rfid("dev-empty", {"rfid": "DEV6"}, devices, manager, db_session, event_suffix=SUFFIX)
    p = _status(manager)
    assert p["status"] == "error"
    assert "Najpierw przyłóż kartę pracownika" in p["message"]


async def test_T2_4_device_no_session_unlinks_and_logs_tx(db_session, devices, manager, reg_manager, set_can_register):
    set_can_register(True)
    e = await make_employee(db_session, "EMP7", wms_login="unl")
    d = await make_device(db_session, "DEV7", "Scan-7", DeviceType.scanner, "S7", employee_id=e.id)
    await process_rfid("dev-un", {"rfid": "DEV7"}, devices, manager, db_session, event_suffix=SUFFIX)
    p = _status(manager)
    assert p["status"] == "success"
    assert "został odpięty" in p["message"]
    await db_session.refresh(d)
    assert d.employee_id is None
    assert await _tx_count(db_session, TransactionType.unregistered) == 1


async def test_T2_5_session_assign_new_type(db_session, devices, manager, reg_manager, set_can_register):
    set_can_register(True)
    e = await make_employee(db_session, "EMP8", wms_login="reg")
    # старт сесії карткою працівника
    await process_rfid("dev-s", {"rfid": "EMP8"}, devices, manager, db_session, event_suffix=SUFFIX)
    d = await make_device(db_session, "DEV8", "Scan-8", DeviceType.scanner, "S8", employee_id=None)
    await process_rfid("dev-s", {"rfid": "DEV8"}, devices, manager, db_session, event_suffix=SUFFIX)
    p = _status(manager)
    assert p["status"] == "success"
    assert "przypisano do reg" in p["message"]
    await db_session.refresh(d)
    assert d.employee_id == e.id
    assert reg_manager.get("dev-s") is not None  # не завершено (лише сканер)
    assert await _tx_count(db_session, TransactionType.registered) == 1


async def test_T2_6_session_same_type_already_owned(db_session, devices, manager, reg_manager, set_can_register):
    set_can_register(True)
    e = await make_employee(db_session, "EMP9", wms_login="own")
    await make_device(db_session, "DEV9a", "Scan-9a", DeviceType.scanner, "S9a", employee_id=e.id)
    await process_rfid("dev-o", {"rfid": "EMP9"}, devices, manager, db_session, event_suffix=SUFFIX)
    d_new = await make_device(db_session, "DEV9b", "Scan-9b", DeviceType.scanner, "S9b", employee_id=None)
    await process_rfid("dev-o", {"rfid": "DEV9b"}, devices, manager, db_session, event_suffix=SUFFIX)
    p = _status(manager)
    assert p["status"] == "error"
    assert "już posiada" in p["message"]
    await db_session.refresh(d_new)
    assert d_new.employee_id is None  # не привʼязано


async def test_T2_7_session_completed_with_both_devices(db_session, devices, manager, reg_manager, set_can_register):
    set_can_register(True)
    e = await make_employee(db_session, "EMP10", wms_login="done")
    await make_device(db_session, "DEV10s", "Sc", DeviceType.scanner, "S10", employee_id=e.id)
    await process_rfid("dev-c", {"rfid": "EMP10"}, devices, manager, db_session, event_suffix=SUFFIX)
    printer = await make_device(db_session, "DEV10p", "Pr", DeviceType.printer, "P10", employee_id=None)
    await process_rfid("dev-c", {"rfid": "DEV10p"}, devices, manager, db_session, event_suffix=SUFFIX)
    p = _status(manager)
    assert p["status"] == "success"
    assert "Rejestracja zakończona" in p["message"]
    assert "skaner Sc" in p["message"]
    assert "drukarkę Pr" in p["message"]
    await db_session.refresh(printer)
    assert printer.employee_id == e.id
    assert reg_manager.get("dev-c") is None  # сесію завершено


async def test_T2_8_unknown_rfid_in_registration_mode(db_session, devices, manager, reg_manager, set_can_register):
    set_can_register(True)
    await process_rfid("dev-z", {"rfid": "NOPE2"}, devices, manager, db_session, event_suffix=SUFFIX)
    p = _status(manager)
    assert p["status"] == "error"
    assert p["message"] == "Nieznany RFID"


# ===========================================================================
# ГРУПА 4 — канал подій (event_suffix)
# ===========================================================================
async def test_T4_1_suffix_routes_events(db_session, devices, manager, reg_manager, set_can_register):
    set_can_register(False)
    # без суфікса → старий канал
    await process_rfid("d", {"rfid": "NOPE"}, devices, manager, db_session, event_suffix="")
    assert manager.last("registration_status") is not None
    assert manager.last("registration_status_v2") is None
    assert manager.last("esp32_data") is not None
