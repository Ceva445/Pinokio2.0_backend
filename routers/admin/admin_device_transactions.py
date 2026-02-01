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

@router.get("")
async def get_device_transactions(
    page: int = Query(1, ge=1),
    user_q: str | None = Query(None),
    device_q: str | None = Query(None),
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
        "items": result.scalars().all(),
        "page": page,
        "pages": pages,
        "total": total
    }
