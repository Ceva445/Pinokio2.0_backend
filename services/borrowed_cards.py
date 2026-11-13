"""Pożyczone karty gościa — wydanie, zwrot i sprzątanie po terminie.

Pracownik, który zostawił kartę w domu, dostaje na zmianę kartę gościa.
Jego własny numer zostaje nietknięty w kadrach: dalej działa, a gdyby karta
się znalazła, wystarczy nią przyłożyć — pożyczka zamyka się sama. Dzięki temu
rejestracje z obu kart trafiają na ten sam rekord pracownika i statystyka nie
rozpada się na dwie osoby.

Czas liczymy w naiwnym UTC, tak samo jak guests.last_used_at.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.db_borrowed_card import (
    POWOD_RECZNY,
    POWOD_TERMIN,
    POWOD_WLASNA_KARTA,
    BorrowedCardDB,
)
from models.db_employee import EmployeeDB
from models.db_guest import DBGuest

logger = logging.getLogger(__name__)

__all__ = [
    "POWOD_RECZNY",
    "POWOD_TERMIN",
    "POWOD_WLASNA_KARTA",
    "teraz_utc",
    "aktywna_po_rfid",
    "aktywna_pracownika",
    "aktywne_pozyczki",
    "wydaj",
    "zwroc",
    "zwolnij_po_terminie",
]


def teraz_utc() -> datetime:
    """Naiwne UTC — w takiej postaci daty leżą w bazie."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def aktywna_po_rfid(db: AsyncSession, rfid: str) -> BorrowedCardDB | None:
    """Trwająca pożyczka tej karty — bez patrzenia na termin.

    Terminem zajmuje się czytający: kartę po czasie trzeba zwolnić, a nie
    udawać, że jej nie ma, bo wtedy zostałaby zajęta do następnego przebiegu
    zadania w tle.
    """
    return (await db.execute(
        select(BorrowedCardDB)
        .options(
            selectinload(BorrowedCardDB.employee).selectinload(EmployeeDB.devices),
            selectinload(BorrowedCardDB.guest),
        )
        .where(BorrowedCardDB.rfid == rfid, BorrowedCardDB.returned_at.is_(None))
        .order_by(BorrowedCardDB.issued_at.desc())
    )).scalars().first()


async def aktywna_pracownika(db: AsyncSession, employee_id: int) -> BorrowedCardDB | None:
    """Trwająca pożyczka tego pracownika — jedna na raz."""
    return (await db.execute(
        select(BorrowedCardDB)
        .options(selectinload(BorrowedCardDB.guest))
        .where(
            BorrowedCardDB.employee_id == employee_id,
            BorrowedCardDB.returned_at.is_(None),
        )
        .order_by(BorrowedCardDB.issued_at.desc())
    )).scalars().first()


async def aktywne_pozyczki(db: AsyncSession) -> list[BorrowedCardDB]:
    """Wszystko, co jest teraz na rękach — do ekranu kierownika."""
    return list((await db.execute(
        select(BorrowedCardDB)
        .options(
            selectinload(BorrowedCardDB.employee),
            selectinload(BorrowedCardDB.guest),
            selectinload(BorrowedCardDB.issued_by),
        )
        .where(BorrowedCardDB.returned_at.is_(None))
        .order_by(BorrowedCardDB.expires_at)
    )).scalars().all())


async def wydaj(
    db: AsyncSession,
    employee: EmployeeDB,
    guest: DBGuest,
    godzin: int,
    issued_by_id: int | None = None,
) -> BorrowedCardDB:
    """Wydać kartę na `godzin`. Numer pracownika zostaje bez zmian.

    Karta idzie w stan „zajęta", żeby nie dało się jej równocześnie wydać
    pracownikowi tymczasowemu — tam karta zastępuje numer na stałe.
    """
    teraz = teraz_utc()
    pozyczka = BorrowedCardDB(
        employee_id=employee.id,
        guest_id=guest.id,
        rfid=guest.rfid,
        issued_at=teraz,
        expires_at=teraz + timedelta(hours=godzin),
        issued_by_id=issued_by_id,
    )
    guest.used = True
    guest.last_used_at = teraz

    db.add(pozyczka)
    db.add(guest)
    await db.commit()
    await db.refresh(pozyczka)

    logger.info(
        "Karta %s pozyczona pracownikowi %s do %s",
        guest.name, employee.wms_login, pozyczka.expires_at,
    )
    return pozyczka


async def zwroc(
    db: AsyncSession,
    pozyczka: BorrowedCardDB,
    powod: str,
    guest: DBGuest | None = None,
    commit: bool = True,
) -> BorrowedCardDB:
    """Zamknąć pożyczkę i oddać kartę do puli.

    Sprzęt zostaje zapisany na pracownika — zdanie urządzenia nie wymaga
    karty, więc odda je własną albo kierownik zdejmie z panelu.
    """
    if pozyczka.returned_at is not None:
        return pozyczka

    if guest is None:
        guest = (await db.execute(
            select(DBGuest).where(DBGuest.id == pozyczka.guest_id)
        )).scalar_one_or_none()

    pozyczka.returned_at = teraz_utc()
    pozyczka.returned_reason = powod
    db.add(pozyczka)

    if guest is not None:
        guest.used = False
        guest.last_used_at = None
        db.add(guest)

    if commit:
        await db.commit()

    logger.info("Karta %s wrocila do puli (%s)",
                guest.name if guest else pozyczka.rfid, powod)
    return pozyczka


async def zwolnij_po_terminie(db: AsyncSession) -> int:
    """Jedno przejście: pożyczki po terminie wracają do puli."""
    teraz = teraz_utc()
    po_terminie = (await db.execute(
        select(BorrowedCardDB)
        .options(selectinload(BorrowedCardDB.guest))
        .where(
            BorrowedCardDB.returned_at.is_(None),
            BorrowedCardDB.expires_at < teraz,
        )
    )).scalars().all()

    for pozyczka in po_terminie:
        await zwroc(db, pozyczka, POWOD_TERMIN, guest=pozyczka.guest, commit=False)

    if po_terminie:
        await db.commit()

    return len(po_terminie)
