import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from httpx import AsyncClient, ASGITransport

from app.main import app
from routers.api import get_devices, get_manager, get_db

from models.device import Device
from models.db_device import DeviceType as DBDeviceType


# =========================
# FIXTURES
# =========================

@pytest.fixture
def fake_device_manager():
    dm = Mock()

    def upd(device_id, data):
        d = Device(device_id)
        d.update_data(data)
        return d

    dm.update_device_data = Mock(side_effect=upd)
    dm.get_device = Mock(side_effect=lambda did: upd(did, {}))
    dm.get_all_devices_status = Mock(return_value={"devices": {}})
    return dm


@pytest.fixture
def fake_connection_manager():
    cm = Mock()
    cm.broadcast_device_data = AsyncMock()
    cm.broadcast_device_list = AsyncMock()
    cm.broadcast_to_all = AsyncMock()
    return cm


@pytest.fixture
async def ac():
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        yield client


# =========================
# FAKE DB
# =========================

class FakeDB:
    def __init__(self):
        self.execute = AsyncMock()
        self.add = Mock()          # ⬅ НЕ AsyncMock
        self.commit = AsyncMock()
        self.refresh = AsyncMock()


def make_result_scalar(val):
    res = Mock()
    res.scalar_one_or_none = Mock(return_value=val)
    res.scalars = Mock(return_value=Mock(all=Mock(return_value=[])))
    return res


def make_result_scalars_list(lst):
    res = Mock()
    res.scalar_one_or_none = Mock(return_value=None)
    res.scalars = Mock(return_value=Mock(all=Mock(return_value=lst)))
    return res


# =========================
# TESTS
# =========================

@pytest.mark.asyncio
async def test_no_rfid_updates_device_and_broadcasts(
    ac, fake_device_manager, fake_connection_manager
):
    app.dependency_overrides[get_devices] = lambda: fake_device_manager
    app.dependency_overrides[get_manager] = lambda: fake_connection_manager
    app.dependency_overrides[get_db] = lambda: FakeDB()

    resp = await ac.post("/api/data/dev-1", json={"temp": 12})

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    fake_connection_manager.broadcast_device_data.assert_awaited()
    fake_connection_manager.broadcast_device_list.assert_awaited()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rfid_matches_employee_starts_session_and_sends_status(
    ac, fake_device_manager, fake_connection_manager
):
    employee = SimpleNamespace(id=1, first_name="Jan", last_name="Kowalski", devices=[])

    fake_db = FakeDB()
    fake_db.execute.return_value = make_result_scalar(employee)

    app.dependency_overrides[get_devices] = lambda: fake_device_manager
    app.dependency_overrides[get_manager] = lambda: fake_connection_manager
    app.dependency_overrides[get_db] = lambda: fake_db

    import app.main as mainmod
    fake_reg = Mock()
    fake_reg.start_or_replace = Mock()
    mainmod.registration_manager = fake_reg

    resp = await ac.post("/api/data/dev-2", json={"rfid": "EMP-RFID"})

    assert resp.status_code == 200
    fake_reg.start_or_replace.assert_called_with("dev-2", employee)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rfid_unknown_returns_error_status(
    ac, fake_device_manager, fake_connection_manager
):
    fake_db = FakeDB()
    fake_db.execute.side_effect = [
        make_result_scalar(None),  # employee
        make_result_scalar(None),  # device
    ]

    app.dependency_overrides[get_devices] = lambda: fake_device_manager
    app.dependency_overrides[get_manager] = lambda: fake_connection_manager
    app.dependency_overrides[get_db] = lambda: fake_db

    import app.main as mainmod
    mainmod.registration_manager = Mock()

    resp = await ac.post("/api/data/dev-3", json={"rfid": "UNKNOWN"})
    assert resp.status_code == 200

    assert any(
        call.args[1]["status"] == "error"
        for call in fake_connection_manager.broadcast_device_data.await_args_list
        if call.args[1]["type"] == "registration_status"
    )

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rfid_device_unlink_when_no_session_and_employee_present(
    ac, fake_device_manager, fake_connection_manager
):
    pass


@pytest.mark.asyncio
async def test_session_exists_and_employee_already_has_same_type(
    ac, fake_device_manager, fake_connection_manager
):
    device_db = SimpleNamespace(
        id=11,
        name="S2",
        type=DBDeviceType.scanner,
        employee_id=None,
    )

    employee = SimpleNamespace(id=2, first_name="A", last_name="B")
    user_device = SimpleNamespace(type=DBDeviceType.scanner)

    fake_db = FakeDB()
    fake_db.execute.side_effect = [
        make_result_scalar(None),               # employee
        make_result_scalar(device_db),          # device
        make_result_scalars_list([user_device]) # user devices
    ]

    app.dependency_overrides[get_devices] = lambda: fake_device_manager
    app.dependency_overrides[get_manager] = lambda: fake_connection_manager
    app.dependency_overrides[get_db] = lambda: fake_db

    import app.main as mainmod
    fake_reg = Mock()
    fake_reg.get = Mock(return_value=SimpleNamespace(employee=employee))
    mainmod.registration_manager = fake_reg

    resp = await ac.post("/api/data/dev-5", json={"rfid": "RFID"})
    assert resp.status_code == 200

    assert any(
        call.args[1]["status"] == "error"
        for call in fake_connection_manager.broadcast_device_data.await_args_list
        if call.args[1]["type"] == "registration_status"
    )

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_session_completion_when_employee_gets_both_devices(
    ac, fake_device_manager, fake_connection_manager
):
    device_db = SimpleNamespace(
        id=12,
        name="P1",
        type=DBDeviceType.printer,
        employee_id=None,
    )

    employee = SimpleNamespace(id=3, first_name="X", last_name="Y")

    scanner = SimpleNamespace(type=DBDeviceType.scanner, name="Sx")
    printer = SimpleNamespace(type=DBDeviceType.printer, name="Px")

    fake_db = FakeDB()
    fake_db.execute.side_effect = [
        make_result_scalar(None),               # employee
        make_result_scalar(device_db),          # device
        make_result_scalars_list([]),            # before
        make_result_scalars_list([scanner, printer])  # after
    ]

    app.dependency_overrides[get_devices] = lambda: fake_device_manager
    app.dependency_overrides[get_manager] = lambda: fake_connection_manager
    app.dependency_overrides[get_db] = lambda: fake_db

    import app.main as mainmod
    fake_reg = Mock()
    fake_reg.get = Mock(return_value=SimpleNamespace(employee=employee))
    fake_reg.end = Mock()
    mainmod.registration_manager = fake_reg

    resp = await ac.post("/api/data/dev-6", json={"rfid": "RFID"})
    assert resp.status_code == 200

    fake_reg.end.assert_called_with("dev-6")
    assert fake_db.add.call_count >= 1

    app.dependency_overrides.clear()
