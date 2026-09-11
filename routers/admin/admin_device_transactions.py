from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from sqlalchemy.orm import joinedload
from datetime import datetime, time

from db.session import get_db
from app.dependencies.admin import require_admin
from models.device_transaction import DeviceChangeTransaction
from models.db_user import UserDB
from models.db_device import DeviceDB

router = APIRouter(
    prefix="/admin/api/device-transactions",
    tags=["Admin Device Transactions"]
)

PAGE_SIZE = 10


def _item(t: DeviceChangeTransaction) -> dict:
    """Wiersz historii zmian — jawną listą pól, nie obiektem ORM.

    Oddawanie modelu wprost wysyłało do przeglądarki całego użytkownika razem
    z password_hash. Ten sam błąd był w historii rejestracji i został tam
    naprawiony w ten sam sposób.
    """
    user, device = t.user, t.device

    return {
        "id": t.id,
        "timestamp": t.timestamp,
        "description": t.description,
        "user": {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
        } if user else None,
        "device": {
            "id": device.id,
            "name": device.name,
        } if device else None,
    }


@router.get("")
async def get_device_transactions(
    page: int = Query(1, ge=1),
    user_q: str | None = Query(None),
    device_q: str | None = Query(None),
    description_q: str | None = Query(
        None,
        description="Fragment opisu zmiany — tak znajduje się stare numery seryjne",
    ),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin)
):
    stmt = (
        select(DeviceChangeTransaction)
        .options(
            joinedload(DeviceChangeTransaction.user),
            joinedload(DeviceChangeTransaction.device)
        )
        .join(DeviceChangeTransaction.user)
        .join(DeviceChangeTransaction.device)
        .order_by(DeviceChangeTransaction.timestamp.desc())
    )

    # 🔍 фільтр по користувачу
    if user_q:
        stmt = stmt.where(
            or_(
                UserDB.username.ilike(f"%{user_q}%"),
                UserDB.first_name.ilike(f"%{user_q}%"),
                UserDB.last_name.ilike(f"%{user_q}%"),
            )
        )

    # 🔍 фільтр по пристрою
    if device_q:
        stmt = stmt.where(
            DeviceDB.name.ilike(f"%{device_q}%")
        )

    # 🔍 фільтр по опису зміни
    #
    # Opis niesie zdanie w rodzaju "changed device serial number XXRBJ231900180
    # to XXRBN245103077", więc stary numer seryjny żyje wyłącznie tutaj — w
    # samym urządzeniu stoi już nowy. Bez tego filtra nie dało się odpowiedzieć
    # na pytanie "co to był za sprzęt", mając na ręku stary SN z faktury.
    if description_q:
        stmt = stmt.where(
            DeviceChangeTransaction.description.ilike(f"%{description_q}%")
        )

    # 📅 дата ВІД
    if date_from:
        stmt = stmt.where(DeviceChangeTransaction.timestamp >= date_from)

    # 📅 дата ДО
    if date_to:
        stmt = stmt.where(
            DeviceChangeTransaction.timestamp <= datetime.combine(
                date_to.date(), time.max
            )
        )

    # 🔢 total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    # 📄 пагінація
    stmt = stmt.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    result = await db.execute(stmt)

    return {
        "items": [_item(t) for t in result.scalars().all()],
        "page": page,
        "pages": pages,
        "total": total
    }
