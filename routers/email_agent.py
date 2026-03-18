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

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, to_email, msg.as_string())
    except Exception as e:
        print("EMAIL ERROR:", e)


@router.post("/send-email")
async def send_email_endpoint(db: AsyncSession = Depends(get_db)):

    now = datetime.now(timezone.utc)
    twelve_hours_ago = now - timedelta(hours=12)

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
            last_registered_subq.c.last_ts < twelve_hours_ago
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