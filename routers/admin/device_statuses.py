from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.dependencies.admin import require_admin
from db.session import get_db
from models.db_device_status import DeviceStatusDB

router = APIRouter(
    prefix="/admin/api/device-statuses",
    tags=["Device Statuses"]
)


# =========================
# GET ALL
# =========================

@router.get("")
async def get_statuses(
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(DeviceStatusDB)
    )

    return result.scalars().all()


# =========================
# GET ONE
# =========================

@router.get("/{status_id}")
async def get_status(
    status_id: int,
    db: AsyncSession = Depends(get_db)
):
    status = await db.get(DeviceStatusDB, status_id)

    if not status:
        raise HTTPException(404, "Status not found")

    return status


# =========================
# CREATE
# =========================

@router.post("")
async def create_status(
    data: dict,
    db: AsyncSession = Depends(get_db)
):
    status = DeviceStatusDB(
        name=data["name"],
        description=data.get("description")
    )

    db.add(status)

    await db.commit()
    await db.refresh(status)

    return status


# =========================
# UPDATE
# =========================

@router.put("/{status_id}")
async def update_status(
    status_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db)
):
    status = await db.get(DeviceStatusDB, status_id)

    if not status:
        raise HTTPException(404, "Status not found")

    status.name = data["name"]
    status.description = data.get("description")

    await db.commit()
    await db.refresh(status)

    return status


# =========================
# DELETE
# =========================

@router.delete("/{status_id}")
async def delete_status(
    status_id: int,
    db: AsyncSession = Depends(get_db)
):
    status = await db.get(DeviceStatusDB, status_id)

    if not status:
        raise HTTPException(404, "Status not found")

    await db.delete(status)
    await db.commit()

    return {"ok": True}

@router.get("/device-statuses")
async def get_device_statuses(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    result = await db.execute(
        select(DeviceStatusDB).order_by(DeviceStatusDB.name)
    )

    statuses = result.scalars().all()

    return [
        {
            "id": s.id,
            "name": s.name
        }
        for s in statuses
    ]