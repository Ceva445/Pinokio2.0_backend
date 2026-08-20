"""Спільні фікстури для тестів бізнес-логіки нового ендпоінта (process_rfid).

Використовуємо РЕАЛЬНУ sqlite (in-memory) через aiosqlite — щоб перевіряти
справжні SQL-запити, звʼязки й транзакції (зокрема фікс гостьового фільтра).
"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

import models  # noqa: F401  — реєструє ВСІ таблиці на Base.metadata
from db.base import Base


# ---------------------------------------------------------------------------
# Реальна тестова БД (sqlite in-memory, свіжа на кожен тест)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session

    await engine.dispose()


# ---------------------------------------------------------------------------
# Фейковий ConnectionManager — перехоплює broadcast-и
# ---------------------------------------------------------------------------
class FakeManager:
    def __init__(self):
        self.events = []            # усі payload-и broadcast_device_data
        self.device_list_calls = 0
        self.connections = {}       # для can_register_on_device (тут не потрібне)

    async def broadcast_device_data(self, device_id, payload):
        self.events.append(payload)

    async def broadcast_device_list(self):
        self.device_list_calls += 1

    def last(self, type_):
        """Останній payload заданого type (або None)."""
        for p in reversed(self.events):
            if p.get("type") == type_:
                return p
        return None


@pytest.fixture
def manager():
    return FakeManager()


@pytest.fixture
def devices():
    """Реальний DeviceManager — він in-memory, БД не чіпає."""
    from managers.device_manager import DeviceManager
    return DeviceManager()


@pytest.fixture
def reg_manager(monkeypatch):
    """Свіжий RegistrationManager на кожен тест (щоб стан не протікав)."""
    from managers.registration_manager import RegistrationManager
    import app.main as mainmod

    rm = RegistrationManager(timeout_seconds=7)
    monkeypatch.setattr(mainmod, "registration_manager", rm)
    return rm


@pytest.fixture
def set_can_register(monkeypatch):
    """Повертає функцію _set(bool), що керує can_register всередині process_rfid.

    Тримаємо allow_registration_without_login=False і підміняємо
    can_register_on_device, щоб напряму задавати дозвіл.
    """
    import routers.api as api

    async def _fake_config(db):
        return {"allow_registration_without_login": False}

    monkeypatch.setattr(api.config_manager, "get_config", _fake_config)

    def _set(value: bool):
        async def _fake_can_register(device_id, manager):
            return value
        monkeypatch.setattr(api, "can_register_on_device", _fake_can_register)

    return _set


# ---------------------------------------------------------------------------
# Фабрики рядків БД
# ---------------------------------------------------------------------------
async def make_employee(db, rfid, wms_login="jkowalski", expired=False):
    from models.db_employee import EmployeeDB
    e = EmployeeDB(
        last_name="Kowalski", first_name="Jan", rfid=rfid, company="ACME",
        wms_login=wms_login, department="WMS", expired=expired,
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def make_device(db, rfid, name, type_, serial, employee_id=None):
    from models.db_device import DeviceDB
    d = DeviceDB(
        name=name, rfid=rfid, serial_number=serial, type=type_,
        employee_id=employee_id,
    )
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return d


async def make_guest(db, rfid, name, used=False):
    from models.db_guest import DBGuest
    g = DBGuest(rfid=rfid, name=name, used=used)
    db.add(g)
    await db.commit()
    await db.refresh(g)
    return g
