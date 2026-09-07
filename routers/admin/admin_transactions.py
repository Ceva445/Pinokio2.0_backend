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
from zoneinfo import ZoneInfo
from models.db_transaction import TransactionType

router = APIRouter(
    prefix="/admin/api/transactions",
    tags=["Admin Transactions"]
)

PAGE_SIZE = 10

# Магазин стоїть у Польщі, а сесія БД працює в UTC. Поле у браузері віддає час
# без зони — це локальний час, який адмін бачить на екрані. Без цієї прив'язки
# введена година поїхала б на 1–2 години і фільтр мовчки показував би не те.
LOCAL_TZ = ZoneInfo("Europe/Warsaw")


def _as_local(moment: datetime) -> datetime:
    """Час із форми — місцевий; уже зонований лишаємо як є."""
    return moment if moment.tzinfo else moment.replace(tzinfo=LOCAL_TZ)

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
            joinedload(TransactionDB.device),
            joinedload(TransactionDB.manager)
        )
        .outerjoin(TransactionDB.employee)
        .join(TransactionDB.device)
        .order_by(TransactionDB.timestamp.desc())
    )

    # 🔍 працівник
    if employee_q:
        stmt = stmt.where(
            or_(
                EmployeeDB.wms_login.ilike(f"%{employee_q}%"),
                EmployeeDB.first_name.ilike(f"%{employee_q}%"),
                EmployeeDB.last_name.ilike(f"%{employee_q}%"),
            )
        )

    # 🔍 пристрій
    if device_q:
        stmt = stmt.where(
            DeviceDB.name.ilike(f"%{device_q}%")
        )

    # 📅 дата ВІД
    if date_from:
        stmt = stmt.where(TransactionDB.timestamp >= _as_local(date_from))

    # 📅 дата ДО — тепер із годиною, тож межу беремо як задано.
    # Виняток — рівно опівніч: у полі без часу це означає "увесь той день",
    # і саме так фільтр поводився досі. Інакше вибір самої дати давав би
    # порожній результат за цей день.
    if date_to:
        if date_to.time() == time.min:
            date_to = datetime.combine(date_to.date(), time.max)
        stmt = stmt.where(TransactionDB.timestamp <= _as_local(date_to))

    # 🔄 тип транзакції
    if tx_type:
        stmt = stmt.where(TransactionDB.type == tx_type)

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
