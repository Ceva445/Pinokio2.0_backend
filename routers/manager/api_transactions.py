from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from sqlalchemy.orm import joinedload

from db.session import get_db
from app.dependencies.admin import require_manager_or_admin
from models.db_transaction import TransactionDB
from models.db_employee import EmployeeDB
from models.db_device import DeviceDB
from datetime import datetime, time
from models.db_transaction import TransactionType

router = APIRouter(
    prefix="/manager/api/transactions",
    tags=["Manager Transactions"]
)

PAGE_SIZE = 10

@router.get("")
async def get_transactions(
    page: int = Query(1, ge=1),
    employee_q: str | None = Query(None),
    device_q: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    tx_type: TransactionType | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_manager_or_admin)
):
    stmt = (
        select(TransactionDB)
        .options(
            joinedload(TransactionDB.employee),
            joinedload(TransactionDB.device)
        )
        .outerjoin(TransactionDB.employee)
        .join(TransactionDB.device)
        .order_by(TransactionDB.timestamp.desc())
    )

    # 🔍 pracownik
    if employee_q:
        stmt = stmt.where(
            or_(
                EmployeeDB.wms_login.ilike(f"%{employee_q}%"),
                EmployeeDB.first_name.ilike(f"%{employee_q}%"),
                EmployeeDB.last_name.ilike(f"%{employee_q}%"),
            )
        )

    # 🔍 urzadzenie
    if device_q:
        stmt = stmt.where(
            DeviceDB.name.ilike(f"%{device_q}%")
        )

    # 📅 data OD
    if date_from:
        stmt = stmt.where(TransactionDB.timestamp >= date_from)

    # 📅 data DO
    if date_to:
        stmt = stmt.where(
            TransactionDB.timestamp <= datetime.combine(
                date_to.date(), time.max
            )
        )

    # 🔄 typ transakcji
    if tx_type:
        stmt = stmt.where(TransactionDB.type == tx_type)

    # 🔢 total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    # 📄 paginacja
    stmt = stmt.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    result = await db.execute(stmt)

    return {
        "items": result.scalars().all(),
        "page": page,
        "pages": pages,
        "total": total
    }
