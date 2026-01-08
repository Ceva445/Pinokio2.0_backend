from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from schemas.device import DeviceType
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

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
    device = devices.update_device_data(device_id, data)

    if device.latest_data:
        await manager.broadcast_device_data(
            device_id,
            {
                "type": "esp32_data",
                "device_id": device_id,
                "data": device.latest_data.data,
            }
        )

    await manager.broadcast_device_list()

    rfid = data.get("rfid")
    ui_message = None
    ui_status = "info"

    if rfid:
        from app.main import registration_manager

        result = await db.execute(
            select(EmployeeDB)
            .options(selectinload(EmployeeDB.devices))
            .where(EmployeeDB.rfid == rfid)
        )
        employee = result.scalar_one_or_none()

        if employee:
            registration_manager.start_or_replace(device_id, employee)
            ui_message = (
                f"Pracownik {employee.first_name} {employee.last_name} aktywny. "
                f"Przyłóż skaner lub drukarkę"
            )
            ui_status = "success"
        else:
            result = await db.execute(
                select(DeviceDB).where(DeviceDB.rfid == rfid)
            )
            device_db = result.scalar_one_or_none()

            if not device_db:
                ui_message = "Nieznany RFID"
                ui_status = "error"
            else:
                session = registration_manager.get(device_id)

                if not session:
                    if device_db.employee_id is not None:
                        device_db.employee_id = None
                        await db.commit()
                        ui_message = f"{device_db.type.value} został odpięty"
                        ui_status = "success"
                    else:
                        ui_message = "Najpierw przyłóż kartę pracownika"
                        ui_status = "error"
                else:
                    employee = session.employee

                    result = await db.execute(
                        select(DeviceDB.type)
                        .where(DeviceDB.employee_id == employee.id)
                    )
                    owned_types = {row[0] for row in result.all()}

                    if device_db.type in owned_types:
                        ui_message = f"Pracownik już posiada {device_db.type.value}"
                        ui_status = "error"
                    else:
                        device_db.employee_id = employee.id
                        await db.commit()

                        result = await db.execute(
                            select(DeviceDB.type)
                            .where(DeviceDB.employee_id == employee.id)
                        )
                        owned_types = {row[0].value for row in result.all()}
                        print(" Owned types ",owned_types)
                        if owned_types == {"scanner", "printer"}:
                            print("ENDING SESSION FOR", device_id)
                            print("BEFORE:", registration_manager.sessions)
                            registration_manager.end(device_id)
                            print("AFTER:", registration_manager.sessions)
                            ui_message = (
                                f"{employee.first_name} {employee.last_name} "
                                f"ma już skaner i drukarkę. Rejestracja zakończona."
                            )
                            ui_status = "success"
                        else:
                            registration_manager.refresh(device_id)
                            ui_message = (
                                f"{device_db.type.value} "
                                f"przypisano do {employee.first_name} {employee.last_name}"
                            )
                            ui_status = "success"

        await manager.broadcast_device_data(
            device_id,
            {
                "type": "registration_status",
                "status": ui_status,
                "message": ui_message,
            },
        )

    return {"status": "ok"}


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
    )

    db.add(employee)
    await db.commit()
    await db.refresh(employee)

    return {
        "id": employee.id,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "company": employee.company,
        "rfid": employee.rfid
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
