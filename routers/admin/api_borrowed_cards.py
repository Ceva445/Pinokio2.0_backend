"""API kart zastępczych: wydanie, podgląd i ręczne zwolnienie.

Pracownik zostawił kartę w domu — kierownik pożycza mu kartę gościa na jedną
zmianę. Numer w kadrach zostaje nietknięty, więc własna karta działa dalej,
a rejestracje z obu trafiają na ten sam rekord.
"""
import logging

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.admin import require_admin, require_manager_or_admin
from db.session import get_db
from managers.config_manager import config_manager
from models.db_borrowed_card import BorrowedCardDB
from models.db_employee import EmployeeDB
from models.db_guest import DBGuest
from services import borrowed_cards

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/api/borrowed-cards",
    tags=["Borrowed cards"],
)


def _wiersz(pozyczka: BorrowedCardDB) -> dict:
    """Jedna pożyczka dla ekranu — polami, nie obiektem ORM.

    Oddanie modelu wprost wysłałoby do przeglądarki całego użytkownika razem
    z hasłem; stąd jawna lista pól, tak samo jak w historii rejestracji.
    """
    pracownik, karta, wydal = pozyczka.employee, pozyczka.guest, pozyczka.issued_by
    zostalo = (pozyczka.expires_at - borrowed_cards.teraz_utc()).total_seconds()

    return {
        "id": pozyczka.id,
        "issued_at": pozyczka.issued_at.isoformat() if pozyczka.issued_at else None,
        "expires_at": pozyczka.expires_at.isoformat() if pozyczka.expires_at else None,
        # Ujemne = termin już minął, a zadanie w tle jeszcze tu nie dotarło.
        "seconds_left": int(zostalo),
        "employee": {
            "id": pracownik.id,
            "wms_login": pracownik.wms_login,
            "first_name": pracownik.first_name,
            "last_name": pracownik.last_name,
            "company": pracownik.company,
        } if pracownik else None,
        "card": {
            "id": karta.id,
            "name": karta.name,
            "rfid": karta.rfid,
        } if karta else None,
        "issued_by": {
            "id": wydal.id,
            "username": wydal.username,
            "first_name": wydal.first_name,
            "last_name": wydal.last_name,
        } if wydal else None,
    }


@router.get("")
async def lista_aktywnych(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_manager_or_admin),
):
    """Karty, które są teraz na rękach."""
    return [_wiersz(p) for p in await borrowed_cards.aktywne_pozyczki(db)]


@router.post("")
async def wydaj_karte(
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_manager_or_admin),
):
    """Pożyczyć wolną kartę gościa pracownikowi, który ma własną kartę."""
    for pole in ("employee_id", "guest_id"):
        if not payload.get(pole):
            raise HTTPException(400, f"Pole '{pole}' jest wymagane")

    pracownik = (await db.execute(
        select(EmployeeDB).where(EmployeeDB.id == int(payload["employee_id"]))
    )).scalar_one_or_none()
    if not pracownik:
        raise HTTPException(404, "Pracownik nie znaleziony")
    if pracownik.expired:
        raise HTTPException(
            400,
            "Pracownik jest zablokowany — blokadę zdejmuje administrator "
            "w edycji pracownika",
        )
    if not pracownik.rfid:
        raise HTTPException(
            400,
            "Ten pracownik nie ma własnej karty. Kartę na stałe wydaje się "
            "przez „Dodaj pracownika tymczasowego”.",
        )

    trwajaca = await borrowed_cards.aktywna_pracownika(db, pracownik.id)
    if trwajaca is not None:
        nazwa = trwajaca.guest.name if trwajaca.guest else trwajaca.rfid
        raise HTTPException(400, f"Pracownik trzyma już kartę zastępczą {nazwa}")

    karta = (await db.execute(
        select(DBGuest).where(DBGuest.id == int(payload["guest_id"]))
    )).scalar_one_or_none()
    if not karta:
        raise HTTPException(404, "Karta nie znaleziona")
    if karta.used:
        raise HTTPException(400, "Ta karta jest już zajęta")

    config = await config_manager.get_config(db)
    godzin = int(config.get("borrowed_card_duration_hours") or 0) or 12

    pozyczka = await borrowed_cards.wydaj(
        db, pracownik, karta, godzin, issued_by_id=user.get("id")
    )

    return {
        "id": pozyczka.id,
        "expires_at": pozyczka.expires_at.isoformat(),
        "hours": godzin,
        "message": (
            f"Karta {karta.name} wydana pracownikowi {pracownik.wms_login} "
            f"na {godzin} h ✅"
        ),
    }


@router.post("/{borrowed_id:int}/return")
async def zwolnij_karte(
    borrowed_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin),
):
    """Ręczne zwolnienie karty przed terminem — tylko administrator."""
    pozyczka = (await db.execute(
        select(BorrowedCardDB).where(BorrowedCardDB.id == borrowed_id)
    )).scalar_one_or_none()
    if not pozyczka:
        raise HTTPException(404, "Pożyczka nie znaleziona")
    if pozyczka.returned_at is not None:
        raise HTTPException(400, "Ta karta już wróciła do puli")

    await borrowed_cards.zwroc(db, pozyczka, borrowed_cards.POWOD_RECZNY)
    logger.info("Karta %s zwolniona recznie przez %s", pozyczka.rfid, user.get("username"))

    return {"message": "Karta wróciła do puli ✅"}
