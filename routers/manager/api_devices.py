"""Podgląd urządzeń dla kierownika — wyłącznie do czytania.

Kierownik ma odnaleźć sprzęt i zobaczyć, u kogo jest. Nie zakłada nowych
urządzeń, nie edytuje istniejących i nie ogląda historii zmian, dlatego ten
router wystawia same GET-y. Endpointy admina zostają nietknięte: to osobna,
węższa ścieżka, a nie poluzowanie tamtych uprawnień.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies.admin import require_manager_or_admin
from db.session import get_db
from models.db_device import DeviceDB, DeviceType
from models.db_device_status import DeviceStatusDB
from models.db_employee import EmployeeDB

router = APIRouter(
    prefix="/manager/api/devices",
    tags=["Manager Devices"]
)


@router.get("/statuses")
async def get_device_statuses(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_manager_or_admin)
):
    """Słownik statusów — tylko do wypełnienia filtra na liście."""
    statuses = (await db.execute(
        select(DeviceStatusDB).order_by(DeviceStatusDB.name)
    )).scalars().all()

    return [{"id": s.id, "name": s.name} for s in statuses]


@router.get("")
async def get_devices(
    q: str | None = Query(default=None, description="Nazwa, numer seryjny, RFID albo osoba"),
    device_type: str | None = Query(default=None, alias="type"),
    status_ids: list[int] = Query(default=[]),
    assigned: str | None = Query(
        default=None,
        description="'assigned' = tylko wydane, 'unassigned' = tylko wolne, brak = wszystkie",
    ),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_manager_or_admin)
):
    """Lista urządzeń z wyszukiwarką. Bez odnośników do edycji — kierownik i tak
    nie wszedłby na ekrany admina, a martwy link wygląda jak awaria."""
    if device_type not in (None, "scanner", "printer"):
        raise HTTPException(status_code=400, detail="type musi być 'scanner' albo 'printer'")

    stmt = (
        select(DeviceDB)
        .outerjoin(DeviceDB.employee)
        .options(
            selectinload(DeviceDB.employee),
            selectinload(DeviceDB.status),
            selectinload(DeviceDB.site),
        )
    )

    if q:
        needle = f"%{q}%"
        # Kierownik częściej pyta "u kogo jest ten skaner" niż o numer seryjny,
        # więc szukamy też po osobie, która sprzęt trzyma.
        stmt = stmt.where(
            or_(
                DeviceDB.name.ilike(needle),
                DeviceDB.serial_number.ilike(needle),
                DeviceDB.rfid.ilike(needle),
                EmployeeDB.wms_login.ilike(needle),
                EmployeeDB.first_name.ilike(needle),
                EmployeeDB.last_name.ilike(needle),
            )
        )

    if device_type:
        stmt = stmt.where(DeviceDB.type == DeviceType(device_type))

    if status_ids:
        stmt = stmt.where(DeviceDB.status_id.in_(status_ids))

    if assigned == "assigned":
        stmt = stmt.where(DeviceDB.employee_id.is_not(None))
    elif assigned == "unassigned":
        stmt = stmt.where(DeviceDB.employee_id.is_(None))

    devices = (await db.execute(stmt.order_by(DeviceDB.name))).scalars().all()

    return [
        {
            "id": d.id,
            "name": d.name,
            "type": d.type.value,
            "serial_number": d.serial_number,
            "rfid": d.rfid,
            "site": d.site.name if d.site else None,
            "status_name": d.status.name if d.status else None,
            "enabled": d.enabled,
            "employee": {
                "wms_login": d.employee.wms_login,
                "first_name": d.employee.first_name,
                "last_name": d.employee.last_name,
                "department": d.employee.department,
            } if d.employee else None,
        }
        for d in devices
    ]
