"""Protokoły uszkodzenia sprzętu.

Kierownik albo administrator wybiera urządzenie, opisuje uszkodzenie i zapisuje
protokół. Zapis idzie do bazy, a jego treść mailem do grupy ALL — czyli do tych
samych adresów, które dostają zbiorcze zestawienie niezwróconego sprzętu.

Kolejność jest tu istotna: najpierw zapis, potem mail. Protokół jest tym, co ma
zostać; nieczynny SMTP nie może skasować zgłoszenia, więc awaria wysyłki wraca
w odpowiedzi jako liczba, a nie jako błąd całego żądania.
"""
import asyncio
import logging
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies.admin import require_admin, require_manager_or_admin
from db.session import get_db
from models.db_damage_report import DamageReportDB
from models.db_department_manager import DepartmentManagerDB
from models.db_device import DeviceDB
from routers.email_agent import DEVICE_TYPE_PL, send_email_sync

logger = logging.getLogger(__name__)

# Magazyn stoi w Polsce; data w mailu ma się zgadzać z tym, co zgłaszający
# widział na ekranie.
LOCAL_TZ = ZoneInfo("Europe/Warsaw")

router = APIRouter(
    prefix="/api/damage-reports",
    tags=["Damage reports"],
)

# Ile protokołów pokazujemy pod formularzem.
PAGE_SIZE = 50

# Grupa odbiorców: ten sam sentynel, którym posługuje się agent mailowy.
ALL_GROUP = "ALL"


async def _all_group_emails(db: AsyncSession) -> list[str]:
    """Adresy grupy ALL, bez powtórzeń niezależnie od wielkości liter."""
    rows = (await db.execute(
        select(DepartmentManagerDB.email).where(
            func.upper(DepartmentManagerDB.department) == ALL_GROUP
        )
    )).scalars().all()

    return list({email.lower(): email for email in rows}.values())


def _message(report: DamageReportDB) -> tuple[str, str]:
    """Temat i treść listu. Wszystko, czego adresat potrzebuje, bez wchodzenia
    do panelu: co, u kogo, kto zgłosił i kiedy."""
    device = report.device
    holder = report.employee
    author = report.user

    device_type = DEVICE_TYPE_PL.get(device.type.value, device.type.value)
    when = report.timestamp.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")

    holder_line = (
        f"{holder.wms_login} ({holder.first_name} {holder.last_name})"
        if holder else "nieprzypisany"
    )
    author_line = (
        f"{author.first_name} {author.last_name} ({author.username})"
        if author else "—"
    )

    subject = f"Protokół uszkodzenia sprzętu — {device.name}"

    message = (
        f"Zgłoszono uszkodzenie sprzętu.\n\n"
        f"Urządzenie: {device_type} {device.name}\n"
        f"Nr seryjny: {device.serial_number}\n"
        f"Pracownik:  {holder_line}\n"
        f"Zgłosił:    {author_line}\n"
        f"Data:       {when}\n\n"
        f"Opis uszkodzenia:\n{report.description}\n"
    )

    return subject, message


def _row(report: DamageReportDB) -> dict:
    device = report.device
    holder = report.employee
    author = report.user

    return {
        "id": report.id,
        "timestamp": report.timestamp,
        "description": report.description,
        "device": {
            "id": device.id,
            "name": device.name,
            "type": device.type.value,
            "serial_number": device.serial_number,
        } if device else None,
        "employee": {
            "wms_login": holder.wms_login,
            "first_name": holder.first_name,
            "last_name": holder.last_name,
        } if holder else None,
        "reported_by": {
            "username": author.username,
            "first_name": author.first_name,
            "last_name": author.last_name,
        } if author else None,
    }


@router.post("")
async def create_damage_report(
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_manager_or_admin),
):
    """Spisanie protokołu i rozesłanie go do grupy ALL."""
    device_id = payload.get("device_id")
    description = (payload.get("description") or "").strip()

    if not device_id:
        raise HTTPException(status_code=400, detail="Wybierz urządzenie")

    if not description:
        raise HTTPException(status_code=400, detail="Opisz uszkodzenie")

    device = (await db.execute(
        select(DeviceDB)
        .where(DeviceDB.id == device_id)
        .options(selectinload(DeviceDB.employee))
    )).scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="Nie ma takiego urządzenia")

    report = DamageReportDB(
        device_id=device.id,
        user_id=user["id"],
        # Posiadacz z chwili zgłoszenia — potem sprzęt i tak zmieni ręce.
        employee_id=device.employee_id,
        description=description,
    )
    db.add(report)
    await db.commit()

    report = (await db.execute(
        select(DamageReportDB)
        .where(DamageReportDB.id == report.id)
        .options(
            selectinload(DamageReportDB.device),
            selectinload(DamageReportDB.employee),
            selectinload(DamageReportDB.user),
        )
    )).scalar_one()

    subject, message = _message(report)
    recipients = await _all_group_emails(db)

    sent = 0
    errors = 0
    for email in recipients:
        try:
            await asyncio.to_thread(send_email_sync, email, subject, message)
            sent += 1
            logger.info("Damage report %s mailed to %s", report.id, email)
        except Exception as exc:
            errors += 1
            logger.error("Damage report %s mail FAILED to %s: %s", report.id, email, exc)

    return {
        "report": _row(report),
        "recipients": len(recipients),
        "sent": sent,
        "errors": errors,
    }


@router.get("")
async def get_damage_reports(
    device_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin),
):
    """Ostatnie protokoły — wyłącznie dla administratora.

    Kierownik zgłasza uszkodzenie i na tym jego rola się kończy; cudze
    zgłoszenia z całego magazynu to nie jest jego widok. Sam zapis dostaje
    potwierdzeniem pod formularzem, a komplet — mailem grupa ALL.
    """
    stmt = (
        select(DamageReportDB)
        .options(
            selectinload(DamageReportDB.device),
            selectinload(DamageReportDB.employee),
            selectinload(DamageReportDB.user),
        )
        .order_by(DamageReportDB.timestamp.desc())
        .limit(PAGE_SIZE)
    )

    if device_id:
        stmt = stmt.where(DamageReportDB.device_id == device_id)

    reports = (await db.execute(stmt)).scalars().all()

    return [_row(r) for r in reports]
