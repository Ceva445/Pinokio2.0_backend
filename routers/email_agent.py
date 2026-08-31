from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta, timezone
import asyncio
import os
import smtplib
import logging
from email.mime.text import MIMEText

from db.session import get_db
from models.db_transaction import TransactionDB, TransactionType
from models.db_employee import EmployeeDB
from models.db_department_manager import DepartmentManagerDB
from models.db_device import DeviceDB

router = APIRouter(tags=["Email Agent"])

logger = logging.getLogger(__name__)

DEVICE_TYPE_PL = {
    "scanner": "skaner",
    "printer": "drukarka"
}

# ---------- SMTP (креди з .env) ----------
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT") or 587)
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM")


def send_email_sync(to_email: str, subject: str, message: str):
    """Синхронна відправка одного листа (викликати через asyncio.to_thread)."""
    msg = MIMEText(message)
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM, [to_email], msg.as_string())


def get_time_threshold(now: datetime, hours: int = 12) -> datetime:
    """
    Отримати часовий поріг для перевірки не повернених пристроїв.
    """
    if now.weekday() == 5:  # Saturday
        return now
    return now - timedelta(hours=hours)


@router.post("/send-email")
async def send_email_endpoint(db: AsyncSession = Depends(get_db)):
    """Ручний тригер (адмін/тест). Планувальник кличе run_email_notifications напряму."""
    return await run_email_notifications(db)


async def run_email_notifications(db: AsyncSession) -> dict:
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

    # ALL-менеджери отримують ЛИШЕ зведений лист → виключаємо їх з відділових,
    # щоб не було дублю (реальні відділи — EMAG/STOCK/XD/…, "ALL" — сентинел)
    all_emails_raw = (
        await db.execute(
            select(DepartmentManagerDB.email).where(
                func.upper(DepartmentManagerDB.department) == "ALL"
            )
        )
    ).scalars().all()
    # Дедуп ALL: регістронезалежно (одна адреса — один лист)
    all_emails = list({e.lower(): e for e in all_emails_raw}.values())
    all_lower = {e.lower() for e in all_emails_raw}

    for department, employees in employees_devices.items():
        managers_stmt = select(DepartmentManagerDB.email).where(
            DepartmentManagerDB.department == department
        )

        result = await db.execute(managers_stmt)
        # виключаємо ALL-менеджерів (регістронезалежно), щоб не дублювати
        manager_emails = [
            e for e in result.scalars().all() if e.lower() not in all_lower
        ]

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

    # 🔹 Один зведений лист для ALL-менеджерів: усі інциденти з усіх відділів
    if employees_devices and all_emails:
        sections = [
            f"[{department}]\n" + "\n".join(employees)
            for department, employees in employees_devices.items()
        ]
        combined_message = (
            f"Zestawienie wszystkich działów — pracownicy {time_text}\n\n"
            + "\n\n".join(sections)
        )
        notifications.append({
            "emails": sorted(all_emails),
            "subject": "Alert zwrotu urządzenia - wszystkie działy",
            "message": combined_message,
        })

    # 🔹 Фактична відправка кожної підготовленої notification
    sent = 0
    errors = 0
    for n in notifications:
        for email in n["emails"]:
            try:
                await asyncio.to_thread(
                    send_email_sync, email, n["subject"], n["message"]
                )
                sent += 1
                logger.info("Return-alert email sent to %s (%s)", email, n["subject"])
            except Exception as exc:
                errors += 1
                logger.error("Email send FAILED to %s: %s", email, exc)

    logger.info(
        "send-email done: notifications=%d sent=%d errors=%d",
        len(notifications), sent, errors
    )

    return {
        "status": "sent",
        "notifications": len(notifications),
        "sent": sent,
        "errors": errors,
    }