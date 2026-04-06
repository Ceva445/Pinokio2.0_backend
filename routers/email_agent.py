from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta, timezone
import asyncio

from db.session import get_db
from models.db_transaction import TransactionDB, TransactionType
from models.db_employee import EmployeeDB
from models.db_department_manager import DepartmentManagerDB
from models.db_device import DeviceDB

router = APIRouter(tags=["Email Agent"])

DEVICE_TYPE_PL = {
    "scanner": "skaner",
    "printer": "drukarka"
}


def get_time_threshold(now: datetime, hours: int = 12) -> datetime:
    """
    Отримати часовий поріг для перевірки не повернених пристроїв.
    """
    if now.weekday() == 5:  # Saturday
        return now
    return now - timedelta(hours=hours)


@router.post("/send-email")
async def send_email_endpoint(db: AsyncSession = Depends(get_db)):
    from managers.config_manager import config_manager
    
    now = datetime.now(timezone.utc)
    
    # Взяти кількість годин з конфіго
    config = await config_manager.get_config(db)
    hours = config.get("device_not_returned_hours", 12)
    
    time_threshold = get_time_threshold(now, hours)
    is_instant_check = time_threshold == now

    # 🔹 subquery: остання registered транзакція для кожного device
    last_registered_subq = (
        select(
            TransactionDB.device_id,
            func.max(TransactionDB.timestamp).label("last_ts")
        )
        .where(TransactionDB.type == TransactionType.registered)
        .group_by(TransactionDB.device_id)
        .subquery()
    )

    # 🔹 головний запит
    stmt = (
        select(
            EmployeeDB.first_name,
            EmployeeDB.last_name,
            EmployeeDB.department,
            DeviceDB.name,
            DeviceDB.type,
            last_registered_subq.c.last_ts
        )
        .join(DeviceDB, DeviceDB.employee_id == EmployeeDB.id)
        .join(last_registered_subq, last_registered_subq.c.device_id == DeviceDB.id)
        .where(
            DeviceDB.employee_id.is_not(None),
            last_registered_subq.c.last_ts < time_threshold
        )
    )

    result = await db.execute(stmt)
    rows = result.all()

    employees_devices: dict[str, list[str]] = {}

    for first_name, last_name, department, device_name, device_type, timestamp in rows:

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        delta = now - timestamp
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)

        device_type_pl = DEVICE_TYPE_PL.get(device_type.value, device_type.value)

        employees_devices.setdefault(department, []).append(
            f"{first_name} {last_name} ({device_type_pl}: {device_name}) — {hours}h {minutes}min"
        )

    # 🔹 email
    notifications = []

    time_text = (
        "nie zwrócili urządzenia (stan na teraz):"
        if is_instant_check
        else "nie zwrócili urządzenia przez ponad 12 godzin:"
    )

    for department, employees in employees_devices.items():
        managers_stmt = select(DepartmentManagerDB.email).where(
            DepartmentManagerDB.department == department
        )

        result = await db.execute(managers_stmt)
        manager_emails = result.scalars().all()

        if not manager_emails:
            continue

        message = (
            f"Pracownicy w Twoim dziale '{department}' {time_text}\n\n"
            + "\n".join(employees)
        )

        subject = f"Alert zwrotu urządzenia - {department}"

        notifications.append({
            "emails": manager_emails,
            "subject": subject,
            "message": message
        })

    return {
        "status": "prepared",
        "notifications": notifications
    }