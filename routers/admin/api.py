from http.client import HTTPException
from fastapi import APIRouter, Depends, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.session import get_db
from app.dependencies.admin import require_admin
from models.db_employee import EmployeeDB

router = APIRouter(
    prefix="/admin/api",
    tags=["Admin API"]
)

@router.get("/employees")
async def get_employees(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    result = await db.execute(select(EmployeeDB))
    return result.scalars().all()


@router.get("/employees/{employee_id}")
async def get_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    result = await db.execute(
        select(EmployeeDB).where(EmployeeDB.id == employee_id)
    )

    employee = result.scalar_one_or_none()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    return employee

@router.put("/employees/{employee_id}")
async def update_employee(
    employee_id: int,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    result = await db.execute(
        select(EmployeeDB).where(EmployeeDB.id == employee_id)
    )
    employee = result.scalar_one_or_none()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Оновлюємо поля, якщо є у payload
    for field in ["first_name", "last_name", "company", "rfid"]:
        if field in payload:
            setattr(employee, field, payload[field])

    await db.commit()
    await db.refresh(employee)

    return employee