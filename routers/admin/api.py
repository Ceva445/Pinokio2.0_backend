from fastapi import APIRouter, Depends, Body, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from db.session import get_db
from app.dependencies.admin import require_admin
from models.db_employee import EmployeeDB
from models.db_device import DeviceDB, DeviceType


router = APIRouter(
    prefix="/admin/api",
    tags=["Admin API"]
)

# ===============================
# CREATE
# ===============================

@router.post("/employees")
async def create_employee(
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    employee = EmployeeDB(
        first_name=payload["first_name"],
        last_name=payload["last_name"],
        company=payload["company"],
        rfid=payload["rfid"],
        wms_login=payload.get("wms_login")
    )

    db.add(employee)
    await db.commit()
    await db.refresh(employee)

    return employee


# ===============================
# LIST + SEARCH
# ===============================

@router.get("/employees")
async def get_employees(
    q: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    stmt = select(EmployeeDB)

    if q:
        stmt = stmt.where(
            or_(
                EmployeeDB.first_name.ilike(f"%{q}%"),
                EmployeeDB.last_name.ilike(f"%{q}%"),
                EmployeeDB.wms_login.ilike(f"%{q}%")
            )
        )

    result = await db.execute(stmt)
    return result.scalars().all()


# ===============================
# GET BY ID
# ===============================

@router.get("/employees/{employee_id:int}")
async def get_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    result = await db.execute(
        select(EmployeeDB).where(EmployeeDB.id == employee_id)
    )

    employee = result.scalar_one_or_none()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    return employee


# ===============================
# UPDATE
# ===============================

@router.put("/employees/{employee_id:int}")
async def update_employee(
    employee_id: int,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    result = await db.execute(
        select(EmployeeDB).where(EmployeeDB.id == employee_id)
    )
    employee = result.scalar_one_or_none()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    for field in ["wms_login", "first_name", "last_name", "company", "rfid"]:
        if field in payload:
            setattr(employee, field, payload[field])

    await db.commit()
    await db.refresh(employee)

    return employee


# ===============================
# DEVICES
# ===============================

@router.post("/devices")
async def create_device(
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    device = DeviceDB(
        name=payload["name"],
        type=DeviceType(payload["type"]),
        serial_number=payload["serial_number"],
        rfid=payload["rfid"]
    )

    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


@router.get("/devices")
async def get_devices(
    q: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    stmt = select(DeviceDB)
    print(stmt)
    if q:
        stmt = stmt.where(
            or_(
                DeviceDB.name.ilike(f"%{q}%"),
                DeviceDB.serial_number.ilike(f"%{q}%"),
                DeviceDB.rfid.ilike(f"%{q}%")
            )
        )

    result = await db.execute(stmt)
    print(result)
    return result.scalars().all()


@router.get("/devices/{device_id:int}")
async def get_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    result = await db.execute(
        select(DeviceDB).where(DeviceDB.id == device_id)
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    return device


@router.put("/devices/{device_id:int}")
async def update_device(
    device_id: int,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    result = await db.execute(
        select(DeviceDB).where(DeviceDB.id == device_id)
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    for field in ["name", "serial_number", "rfid", "type"]:
        if field in payload:
            value = (
                DeviceType(payload[field])
                if field == "type"
                else payload[field]
            )
            setattr(device, field, value)

    await db.commit()
    await db.refresh(device)
    return device


@router.delete("/devices/{device_id:int}")
async def delete_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    result = await db.execute(
        select(DeviceDB).where(DeviceDB.id == device_id)
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    await db.delete(device)
    await db.commit()
