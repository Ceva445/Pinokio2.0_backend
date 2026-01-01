from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from managers.connection_manager import ConnectionManager
from managers.device_manager import DeviceManager

from db.session import get_db
from models.db_employee import EmployeeDB
from models.db_device import DeviceDB

router = APIRouter(prefix="/api", tags=["API"])


# ---------- DEPENDENCIES ----------

def get_manager():
    from app.main import manager
    return manager


def get_devices():
    from app.main import device_manager
    return device_manager


# ---------- ENDPOINT ----------

@router.post("/data/{device_id}")
async def receive_esp32_data(
    device_id: str,
    data: Dict[str, Any],
    devices: DeviceManager = Depends(get_devices),
    manager: ConnectionManager = Depends(get_manager),
    db: AsyncSession = Depends(get_db),
):
    devices.update_device_data(device_id, data)

    rfid_info = None
    rfid = data.get("rfid")

    if rfid:
        # 🔹 Перевіряємо працівника
        result = await db.execute(
            select(EmployeeDB).where(EmployeeDB.rfid == rfid)
        )
        employee = result.scalar_one_or_none()

        if employee:
            rfid_info = {
                "type": "employee",
                "id": employee.id,
                "first_name": employee.first_name,
                "last_name": employee.last_name,
                "company": employee.company,
            }
        else:
            # 🔹 Якщо не працівник — перевіряємо пристрій
            result = await db.execute(
                select(DeviceDB).where(DeviceDB.rfid == rfid)
            )
            device_db = result.scalar_one_or_none()

            if device_db:
                rfid_info = {
                    "type": "device",
                    "id": device_db.id,
                    "name": device_db.name,
                    "device_type": device_db.type.value,
                }

    await manager.broadcast_device_list()

    payload = data.copy()
    if rfid_info:
        payload["rfid_info"] = rfid_info

    await manager.broadcast_device_data(
        device_id,
        {
            "type": "esp32_data",
            "device_id": device_id,
            "data": payload,
            "rfid_info": rfid_info,
        },
    )

    return {
        "status": "ok",
        "rfid_info": rfid_info,
    }


# ---------- EMPLOYEES ----------

@router.post("/employees", status_code=status.HTTP_201_CREATED)
async def create_employee(
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
):
    rfid = payload.get("rfid")
    if not rfid:
        raise HTTPException(400, "rfid is required")

    result = await db.execute(
        select(EmployeeDB).where(EmployeeDB.rfid == rfid)
    )
    if result.scalar_one_or_none():
        raise HTTPException(409, "Employee with this RFID already exists")

    employee = EmployeeDB(
        first_name=payload.get("first_name"),
        last_name=payload.get("last_name"),
        company=payload.get("company"),
        rfid=rfid,
        device_id=payload.get("device_id"),
    )

    db.add(employee)
    await db.commit()
    await db.refresh(employee)

    return {
        "id": employee.id,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "company": employee.company,
        "rfid": employee.rfid,
        "device_id": employee.device_id,
    }


# ---------- DEVICES ----------

@router.post("/devices", status_code=status.HTTP_201_CREATED)
async def create_device(
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
):
    rfid = payload.get("rfid")
    if not rfid:
        raise HTTPException(400, "rfid is required")

    result = await db.execute(
        select(DeviceDB).where(DeviceDB.rfid == rfid)
    )
    if result.scalar_one_or_none():
        raise HTTPException(409, "Device with this RFID already exists")

    device = DeviceDB(
        name=payload.get("name"),
        rfid=rfid,
        serial_number=payload.get("serial_number"),
        type=payload.get("type"),
    )

    db.add(device)
    await db.commit()
    await db.refresh(device)

    return {
        "id": device.id,
        "name": device.name,
        "rfid": device.rfid,
        "serial_number": device.serial_number,
        "type": device.type,
    }
