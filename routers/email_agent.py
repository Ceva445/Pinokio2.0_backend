from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta, timezone
import asyncio

from db.session import get_db
from models.db_transaction import TransactionDB, TransactionType
from models.db_employee import EmployeeDB
from models.db_department_manager import DepartmentManagerDB
from models.db_device import DeviceDB

import smtplib
from email.mime.text import MIMEText
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(tags=["Email Agent"])

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM")

DEVICE_TYPE_PL = {
    "scanner": "skaner",
    "printer": "drukarka"
}


def send_email_sync(to_email: str, subject: str, message: str):
    msg = MIMEText(message)
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM, to_email, msg.as_string())


@router.post("/send-email")
async def send_email_endpoint(db: AsyncSession = Depends(get_db)):

    now = datetime.now(timezone.utc)
    twelve_hours_ago = now - timedelta(hours=12)

    stmt = (
        select(
            EmployeeDB.first_name,
            EmployeeDB.last_name,
            EmployeeDB.department,
            DeviceDB.name,
            DeviceDB.type,
            TransactionDB.timestamp
        )
        .join(TransactionDB, EmployeeDB.id == TransactionDB.employee_id)
        .join(DeviceDB, DeviceDB.id == TransactionDB.device_id)
        .where(
            TransactionDB.type == TransactionType.registered,
            TransactionDB.timestamp < twelve_hours_ago
        )
    )

    result = await db.execute(stmt)
    transactions = result.all()

    employees_devices: dict[str, list[str]] = {}

    for first_name, last_name, department, device_name, device_type, timestamp in transactions:

        last_event_stmt = (
            select(TransactionDB.type)
            .join(DeviceDB, DeviceDB.id == TransactionDB.device_id)
            .where(DeviceDB.name == device_name)
            .order_by(TransactionDB.timestamp.desc())
            .limit(1)
        )

        last_event_result = await db.execute(last_event_stmt)
        last_event = last_event_result.scalar_one_or_none()

        if last_event == TransactionType.unregistered:
            continue

        # обрахунок часу
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        hours = int((now - timestamp).total_seconds() // 3600)
        minutes = int(((now - timestamp).total_seconds() % 3600) // 60)

        device_type_pl = DEVICE_TYPE_PL.get(device_type.value, device_type.value)

        if department not in employees_devices:
            employees_devices[department] = []

        employees_devices[department].append(
            f"{first_name} {last_name} ({device_type_pl}: {device_name}) — {hours}h {minutes}min"
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
            f"Pracownicy w Twoim dziale '{department}' nie zwrócili urządzenia przez ponad 12 godzin:\n\n"
            + "\n".join(employees)
        )

        subject = f"Alert zwrotu urządzenia - {department}"

        for email in manager_emails:
            await asyncio.to_thread(send_email_sync, email, subject, message)

    return {
        "status": "emails sent automatically",
        "departments_notified": list(employees_devices.keys())
    }