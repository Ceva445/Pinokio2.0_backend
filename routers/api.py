from fastapi import APIRouter, Depends, HTTPException
from fastapi import status
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from managers.connection_manager import ConnectionManager
from managers.device_manager import DeviceManager
from db.session import get_db
from models.db_employee import EmployeeDB
from models.db_device import DeviceDB, DeviceType
from models.db_transaction import TransactionDB
from models.db_transaction import TransactionType as DbTransactionType
from schemas.transaction import TransactionType
from routers.auth import get_current_user
from config import ALLOW_REGISTRATION_WITHOUT_LOGIN

router = APIRouter(prefix="/api", tags=["API"])

# ---------- DEPENDENCIES ----------

def get_manager():
    from app.main import manager
    return manager


def get_devices():
    from app.main import device_manager
    return device_manager


# ===============================
# REGISTRATION PERMISSION CHECK (STRICT AND)
# ===============================
async def can_register_on_device(
    device_id: str,
    manager,
):
    """
    Дозвіл на реєстрацію якщо:
    - є user у esp_allowed_users
    - І є websocket слухач цього ESP
    """

    from app.main import esp_allowed_users

    # users які дозволили реєстрацію
    device_users = esp_allowed_users.get(device_id, set())
    if not device_users:
        return False

    # websocket слухачі
    listeners = [
        ws for ws, subscribed in manager.connections.items()
        if subscribed == device_id
    ]

    if not listeners:
        return False

    return True


# ---------- DATA ENDPOINT (ESP32) ----------

@router.post("/data/{device_id}")
async def receive_esp32_data(
    device_id: str,
    data: Dict[str, Any],
    devices: DeviceManager = Depends(get_devices),
    manager: ConnectionManager = Depends(get_manager),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user(False)),

):
    from app.main import registration_manager, esp_allowed_users

    device = devices.update_device_data(device_id, data)

    # 🔄 Broadcast ESP data
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
    print("Allwed devices:", esp_allowed_users)
    print("Current user:", current_user)
    # 🔐 Czy rejestracja dozwolona
    if ALLOW_REGISTRATION_WITHOUT_LOGIN:
        can_register = True
    else:
        can_register = await can_register_on_device(device_id, manager)

        print("Allwed devices:", esp_allowed_users)
        print("Current user:", current_user)
        print("Can register:", can_register)
    print("Can register:", can_register)
    rfid = data.get("rfid")
    ui_message = None
    ui_status = "info"

    if not rfid:
        return {"status": "ok"}

    # ---------- EMPLOYEE ----------
    result = await db.execute(
        select(EmployeeDB)
        .options(selectinload(EmployeeDB.devices))
        .where(EmployeeDB.rfid == rfid)
    )
    employee = result.scalar_one_or_none()

    if employee:
        if can_register:
            registration_manager.start_or_replace(device_id, employee)
            ui_message = (
                f"Pracownik {employee.first_name} {employee.last_name} aktywny. "
                f"Przyłóż skaner lub drukarkę"
            )
            print("ui message:", ui_message)
            ui_status = "success"
        else:
            result = await db.execute(
                    select(DeviceDB).where(DeviceDB.employee_id == employee.id)
                )
            print("Employee devices query result:", result)
            user_devices = result.scalars().all()
            
            ui_message = (
                f"Pracownik {employee.first_name} {employee.last_name} posiada. "
                f"{', '.join([f'{d.type.value}: {d.name}' for d in user_devices])}. "
            )
            print("ui message:", ui_message)
            ui_status = "info"

    else:
        # ---------- DEVICE ----------
        result = await db.execute(
            select(DeviceDB).where(DeviceDB.rfid == rfid)
        )
        device_db = result.scalar_one_or_none()

        if not device_db:
            ui_message = "Nieznany RFID"
            ui_status = "error"

        else:
            if not can_register:
                if device_db.employee_id is None:
                    ui_message = (
                        f"{device_db.type.value} {device_db.name} nie jest przypisany do nikogo. "
                    )
                    ui_status = "info"
                else:
                    employee_full_name = await db.execute(
                        select(EmployeeDB).where(EmployeeDB.id == device_db.employee_id)
                    )
                    employee_full_name = employee_full_name.scalar_one_or_none()
                    ui_message = (
                        f"{device_db.type.value} {device_db.name} "
                        f"należy do {employee_full_name.first_name} {employee_full_name.last_name}. "
                        f"Brak uprawnień do rejestracji."
                    )
                    ui_status = "info"
            else:
                session = registration_manager.get(device_id)

                # ❌ brak sesji pracownika
                if not session:
                    if device_db.employee_id is not None:
                        device_db.employee_id = None
                        await db.commit()

                        ui_message = f"{device_db.type.value} {device_db.name} został odpięty"
                        ui_status = "success"

                        transaction = TransactionDB(
                            type=TransactionType.unregistered,
                            device_id=device_db.id,
                            employee_id=None
                        )
                        db.add(transaction)
                        await db.commit()
                    else:
                        ui_message = "Najpierw przyłóż kartę pracownika"
                        ui_status = "error"

                else:
                    employee = session.employee

                    result = await db.execute(
                        select(DeviceDB).where(DeviceDB.employee_id == employee.id)
                    )
                    user_devices = result.scalars().all()
                    owned_types = {d.type for d in user_devices}

                    if device_db.type in owned_types:
                        ui_message = (
                            f"Pracownik już posiada {device_db.type.value} {device_db.name}"
                        )
                        ui_status = "error"
                    else:
                        device_db.employee_id = employee.id
                        await db.commit()

                        result = await db.execute(
                            select(DeviceDB)
                            .where(DeviceDB.employee_id == employee.id)
                        )
                        user_devices = result.scalars().all()
                        owned_types = {d.type.value for d in user_devices}

                        if owned_types == {"scanner", "printer"}:
                            registration_manager.end(device_id)

                            scanner = next(d for d in user_devices if d.type.value == DeviceType.scanner.value)
                            printer = next(d for d in user_devices if d.type.value == DeviceType.printer.value)                         
                            ui_message = (
                                f"{employee.first_name} {employee.last_name} "
                                f"ma już skaner {scanner.name} i drukarkę {printer.name}. "
                                f"Rejestracja zakończona."
                            )
                            ui_status = "success"
                            transaction = TransactionDB(
                                type=TransactionType.registered,
                                device_id=device_db.id,
                                employee_id=employee.id
                            )
                            db.add(transaction)
                            await db.commit()
                        else:
                            registration_manager.refresh(device_id)
                            ui_message = (
                                f"{device_db.type.value} {device_db.name} "
                                f"przypisano do {employee.first_name} {employee.last_name}"
                            )
                            ui_status = "success"
                            transaction = TransactionDB(
                                type=TransactionType.registered,
                                device_id=device_db.id,
                                employee_id=employee.id
                            )
                            db.add(transaction)
                            await db.commit()

    await manager.broadcast_device_data(
        device_id,
        {
            "type": "registration_status",
            "status": ui_status,
            "message": ui_message,
        },
    )

    return {"status": "ok"}


# ---------- ESP SUBSCRIBE / UNSUBSCRIBE ----------

@router.post("/subscribe-esp/{esp_id}")
async def subscribe_esp(
    esp_id: str,
    current_user: dict = Depends(get_current_user())
):
    from app.main import esp_allowed_users

    if esp_id not in esp_allowed_users:
        esp_allowed_users[esp_id] = set()

    esp_allowed_users[esp_id].add(current_user["id"])

    return {
        "status": "success",
        "message": f"User {current_user['username']} can now register devices on ESP {esp_id}",
    }


@router.post("/unsubscribe-esp/{esp_id}")
async def unsubscribe_esp(
    esp_id: str,
    current_user: dict = Depends(get_current_user())
):
    from app.main import esp_allowed_users

    if esp_id in esp_allowed_users:
        esp_allowed_users[esp_id].discard(current_user["id"])
        if not esp_allowed_users[esp_id]:
            esp_allowed_users.pop(esp_id)

    return {
        "status": "success",
        "message": f"User {current_user['username']} stopped listening to ESP {esp_id}",
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


@router.post("/end-session/{device_id}")
async def end_session(device_id: str):
    from app.main import registration_manager

    session = registration_manager.get(device_id)
    if not session:
        return {"status": "error", "message": "Brak aktywnej sesji"}

    registration_manager.sessions.pop(device_id, None)
    return {
        "status": "success",
        "message": f"Sesja dla {device_id} zakończona",
    }
