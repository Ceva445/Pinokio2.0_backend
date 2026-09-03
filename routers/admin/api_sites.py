"""CRUD довідника майданчиків (sites).

Замінює колишній enum SiteType: адмін може перейменовувати наявні майданчики
та додавати нові прямо з панелі, без міграцій і релізу.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app.dependencies.admin import require_admin, require_manager_or_admin
from db.session import get_db
from models.db_site import SiteDB
from models.db_device import DeviceDB
from models.db_employee import EmployeeDB

router = APIRouter(
    prefix="/admin/api/sites",
    tags=["Admin Sites"]
)


def _serialize(site: SiteDB, devices_count: int | None = None) -> dict:
    data = {
        "id": site.id,
        "name": site.name,
        "description": site.description,
        "enabled": site.enabled,
    }
    if devices_count is not None:
        data["devices_count"] = devices_count
    return data


@router.get("")
async def list_sites(
    only_enabled: bool = False,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_manager_or_admin),
):
    """Список майданчиків із кількістю привʼязаних пристроїв.

    Читання доступне і менеджеру — форма тимчасового працівника
    (/manager/temporary-employees/create) теж показує вибір site.
    Створення, зміна й видалення лишаються тільки для адміна.
    """
    stmt = (
        select(SiteDB, func.count(DeviceDB.id))
        .outerjoin(DeviceDB, DeviceDB.site_id == SiteDB.id)
        .group_by(SiteDB.id)
        .order_by(SiteDB.name)
    )
    if only_enabled:
        stmt = stmt.where(SiteDB.enabled.is_(True))

    rows = (await db.execute(stmt)).all()
    return [_serialize(site, count) for site, count in rows]


@router.post("")
async def create_site(
    data: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin),
):
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Nazwa site jest wymagana")

    site = SiteDB(
        name=name,
        description=(data.get("description") or "").strip() or None,
        enabled=bool(data.get("enabled", True)),
    )
    db.add(site)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(400, f"Site '{name}' już istnieje")

    await db.refresh(site)
    return _serialize(site, 0)


@router.put("/{site_id}")
async def update_site(
    site_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin),
):
    site = await db.get(SiteDB, site_id)
    if not site:
        raise HTTPException(404, "Site nie znaleziony")

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "Nazwa site jest wymagana")
        site.name = name

    if "description" in data:
        site.description = (data.get("description") or "").strip() or None

    if "enabled" in data:
        site.enabled = bool(data["enabled"])

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(400, f"Site '{data.get('name')}' już istnieje")

    await db.refresh(site)
    return _serialize(site)


@router.delete("/{site_id}")
async def delete_site(
    site_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin),
):
    site = await db.get(SiteDB, site_id)
    if not site:
        raise HTTPException(404, "Site nie znaleziony")

    # Не даємо видалити майданчик, до якого щось привʼязане — інакше
    # FK віддав би 500 замість зрозумілого повідомлення.
    devices_used = (await db.execute(
        select(func.count(DeviceDB.id)).where(DeviceDB.site_id == site_id)
    )).scalar_one()
    employees_used = (await db.execute(
        select(func.count(EmployeeDB.id)).where(EmployeeDB.site_id == site_id)
    )).scalar_one()

    if devices_used or employees_used:
        parts = []
        if devices_used:
            parts.append(f"{devices_used} urządzeń")
        if employees_used:
            parts.append(f"{employees_used} pracowników")
        raise HTTPException(
            400,
            f"Nie można usunąć: site '{site.name}' jest przypisany do "
            f"{' i '.join(parts)}. Zmień przypisanie lub wyłącz ten site."
        )

    await db.delete(site)
    await db.commit()
    return {"ok": True}
