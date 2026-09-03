"""Тести довідника site (заміна enum SiteType на модель)."""
import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio


async def _make_site(db, name, enabled=True):
    from models.db_site import SiteDB
    s = SiteDB(name=name, enabled=enabled)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def test_resolve_site_by_name(db_session):
    """Назва site (як шле адмінка й синхронізація з Sheets) → site_id."""
    from routers.admin.api import resolve_site_id
    site = await _make_site(db_session, "EMAG")
    assert await resolve_site_id(db_session, {"site": "EMAG"}) == site.id


async def test_resolve_site_by_id(db_session):
    from routers.admin.api import resolve_site_id
    site = await _make_site(db_session, "XD")
    assert await resolve_site_id(db_session, {"site_id": site.id}) == site.id


async def test_resolve_unknown_site_gives_400(db_session):
    """Невідома назва — зрозуміла помилка зі списком доступних, а не 500."""
    from routers.admin.api import resolve_site_id
    await _make_site(db_session, "STOCK")
    with pytest.raises(HTTPException) as exc:
        await resolve_site_id(db_session, {"site": "NIE_ISTNIEJE"})
    assert exc.value.status_code == 400
    assert "STOCK" in exc.value.detail


async def test_resolve_empty_site_is_none(db_session):
    from routers.admin.api import resolve_site_id
    assert await resolve_site_id(db_session, {}) is None
    assert await resolve_site_id(db_session, {"site": ""}) is None


async def test_rename_site_propagates_to_devices(db_session):
    """Перейменування site видно на всіх його пристроях (FK, а не копія рядка)."""
    from models.db_device import DeviceDB, DeviceType
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    site = await _make_site(db_session, "OLD_NAME")
    db_session.add(DeviceDB(
        name="SCAN-1", rfid="R1", serial_number="S1",
        type=DeviceType.scanner, site_id=site.id,
    ))
    await db_session.commit()

    site.name = "NEW_NAME"
    await db_session.commit()

    device = (await db_session.execute(
        select(DeviceDB).options(selectinload(DeviceDB.site))
        .where(DeviceDB.name == "SCAN-1")
    )).scalar_one()
    assert device.site.name == "NEW_NAME"


async def test_device_out_serializes_site_name(db_session):
    """DeviceOut віддає назву site, а не обʼєкт."""
    from models.db_device import DeviceDB, DeviceType
    from schemas.device import DeviceOut
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    site = await _make_site(db_session, "KONTROLA")
    db_session.add(DeviceDB(
        name="SCAN-2", rfid="R2", serial_number="S2",
        type=DeviceType.scanner, site_id=site.id,
    ))
    await db_session.commit()

    device = (await db_session.execute(
        select(DeviceDB).options(selectinload(DeviceDB.site))
        .where(DeviceDB.name == "SCAN-2")
    )).scalar_one()

    assert DeviceOut.model_validate(device).site == "KONTROLA"


async def test_employee_site_relationship(db_session):
    """Працівник привʼязується до site, перейменування site видно на ньому."""
    from models.db_employee import EmployeeDB
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    site = await _make_site(db_session, "EMAG_EMP")
    db_session.add(EmployeeDB(
        last_name="Kowalski", first_name="Jan", rfid="EMP-RF-1",
        company="ACME", wms_login="jkow", department="WMS", site_id=site.id,
    ))
    await db_session.commit()

    site.name = "EMAG_EMP_2"
    await db_session.commit()

    emp = (await db_session.execute(
        select(EmployeeDB).options(selectinload(EmployeeDB.site))
        .where(EmployeeDB.wms_login == "jkow")
    )).scalar_one()
    assert emp.site.name == "EMAG_EMP_2"


async def test_site_lists_its_employees(db_session):
    """Зворотний звʼязок site → employees працює."""
    from models.db_employee import EmployeeDB
    from models.db_site import SiteDB
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    site = await _make_site(db_session, "STOCK_EMP")
    for i in (1, 2):
        db_session.add(EmployeeDB(
            last_name=f"N{i}", first_name=f"F{i}", rfid=f"EMP-RF-{i}0",
            company="ACME", wms_login=f"log{i}", site_id=site.id,
        ))
    await db_session.commit()

    loaded = (await db_session.execute(
        select(SiteDB).options(selectinload(SiteDB.employees))
        .where(SiteDB.id == site.id)
    )).scalar_one()
    assert len(loaded.employees) == 2
