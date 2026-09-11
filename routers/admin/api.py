from fastapi import APIRouter, Depends, Body, Query, HTTPException
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from models.db_department_manager import DepartmentManagerDB
from models.db_guest import DBGuest
from models.device_transaction import DeviceChangeTransaction
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, or_, and_

from datetime import timezone
from zoneinfo import ZoneInfo

from db.session import get_db
from app.dependencies.admin import (
    require_admin,
    require_dashboard_viewer,
    require_manager_or_admin,
)
from models.db_employee import EmployeeDB
from models.db_device import DeviceDB, DeviceType
from models.db_site import SiteDB
from models.db_port import DevicePortDB
from models.db_device_status import DeviceStatusDB
from models.db_transaction import TRANSACTION_SOURCE_PANEL, TransactionDB, TransactionType
from services.device_transactions import build_change_descriptions, create_device_transaction
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/api",
    tags=["Admin API"]
)

# ===============================
# CREATE
# ===============================

async def resolve_site_id(db: AsyncSession, payload: dict) -> int | None:
    """Визначити site_id з payload.

    Приймає або site_id (число), або site (назва) — назву використовують
    існуючі клієнти й скрипт синхронізації з Google Sheets, тому контракт
    API лишається сумісним після переходу з enum на довідник.
    """
    if payload.get("site_id") not in (None, "", "null"):
        try:
            site_id = int(payload["site_id"])
        except (TypeError, ValueError):
            raise HTTPException(400, "Nieprawidłowy site")
        if not await db.get(SiteDB, site_id):
            raise HTTPException(400, "Site nie znaleziony")
        return site_id

    name = payload.get("site")
    if name in (None, ""):
        return None

    site = (await db.execute(
        select(SiteDB).where(SiteDB.name == str(name).strip())
    )).scalar_one_or_none()

    if not site:
        available = (await db.execute(select(SiteDB.name).order_by(SiteDB.name))).scalars().all()
        raise HTTPException(
            400,
            f"Site musi być jeden z: {', '.join(available) or 'brak zdefiniowanych site'}"
        )
    return site.id


@router.post("/employees")
async def create_employee(
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    try:
        # Validate required fields
        required_fields = ["first_name", "last_name", "company", "rfid"]
        for field in required_fields:
            if field not in payload or not payload[field]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Pole '{field}' jest wymagane"
                )
        
        employee = EmployeeDB(
            first_name=payload["first_name"].strip(),
            last_name=payload["last_name"].strip(),
            company=payload["company"].strip(),
            rfid=payload["rfid"].strip(),
            wms_login=payload.get("wms_login", "").strip(),
            site_id=await resolve_site_id(db, payload)
        )

        db.add(employee)
        await db.commit()
        await db.refresh(employee)
        return employee
        
    except IntegrityError as e:
        await db.rollback()
        if "unique constraint" in str(e).lower():
            raise HTTPException(
                status_code=400,
                detail="Pracownik z tymi danymi już istnieje"
            )
        raise HTTPException(
            status_code=400,
            detail="Błąd bazy danych: dane są nieprawidłowe"
        )
    except ValueError as e:
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Błąd walidacji: {str(e)}"
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Wewnętrzny błąd serwera"
        )


# ===============================
# LIST + SEARCH
# ===============================

@router.get("/employees")
async def get_employees(
    q: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    stmt = select(EmployeeDB)

    if q:
        stmt = stmt.where(
            or_(
                EmployeeDB.first_name.ilike(f"%{q}%"),
                EmployeeDB.last_name.ilike(f"%{q}%"),
                EmployeeDB.wms_login.ilike(f"%{q}%")
            )
        )
    # Po loginie WMS, bo to jedyny klucz wpisywany bez wariantów: w danych
    # z produkcji imię i nazwisko bywają zamienione miejscami.
    stmt = stmt.order_by(EmployeeDB.wms_login)
    result = await db.execute(stmt)
    return result.scalars().all()


# ===============================
# GET BY ID
# ===============================

@router.get("/employees/{employee_id:int}")
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


# ===============================
# UPDATE
# ===============================

@router.put("/employees/{employee_id:int}")
async def update_employee(
    employee_id: int,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    try:
        result = await db.execute(
            select(EmployeeDB).where(EmployeeDB.id == employee_id)
        )
        employee = result.scalar_one_or_none()

        if not employee:
            raise HTTPException(status_code=404, detail="Pracownik nie znaleziony")

        # site може прийти назвою або site_id — зводимо до site_id
        if "site" in payload or "site_id" in payload:
            payload["site_id"] = await resolve_site_id(db, payload)

        do_unexpire = False
        for field in ["wms_login", "first_name", "last_name", "company", "rfid", "expired", "site_id"]:
            if field in payload:
                value = payload[field]

                if field == "rfid":
                    # Get both guests in parallel and batch the updates
                    old_guest_result = await db.execute(
                        select(DBGuest).where(DBGuest.rfid == employee.rfid)
                    )
                    old_guest = old_guest_result.scalar_one_or_none()
                    
                    new_guest_result = await db.execute(
                        select(DBGuest).where(DBGuest.rfid == value)
                    )
                    new_guest = new_guest_result.scalar_one_or_none()
                    
                    # Batch all updates before committing once
                    if old_guest and old_guest.used:
                        old_guest.used = False
                        old_guest.last_used_at = None
                        do_unexpire = True  # Unexpire employee if RFID is changing from an expired one
                    
                    if new_guest:
                        new_guest.used = True
                        new_guest.last_used_at = func.now()
                    
                    # Single commit for both changes
                    await db.commit()
                if isinstance(value, str):
                    value = value.strip()
                setattr(employee, field, value)             
        
        if do_unexpire:
            employee.expired = False
            
        await db.commit()
        await db.refresh(employee)
        return employee
        
    except IntegrityError as e:
        await db.rollback()
        if "unique constraint" in str(e).lower():
            raise HTTPException(
                status_code=400,
                detail="Pracownik z tymi danymi już istnieje"
            )
        raise HTTPException(
            status_code=400,
            detail="Błąd bazy danych: dane są nieprawidłowe"
        )
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Wewnętrzny błąd serwera"
        )

@router.delete("/employees/{employee_id:int}")
async def delete_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    try:
        result = await db.execute(
            select(EmployeeDB).where(EmployeeDB.id == employee_id)
        )
        employee = result.scalar_one_or_none()

        if not employee:
            raise HTTPException(status_code=404, detail="Pracownik nie znaleziony")

        await db.delete(employee)
        await db.commit()
        return {"message": "Pracownik został usunięty ✅"}

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Wewnętrzny błąd serwera"
        )

# ===============================
# TEMPORARY EMPLOYEES
# ===============================

@router.get("/guests")
async def get_guests(
    q: str | None = Query(default=None),
    unused_only: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_manager_or_admin)
):
    """Get guests for temporary employee creation or admin management"""     
    stmt = select(DBGuest)
    
    # Filter by used status if requested
    if unused_only:
        stmt = stmt.where(DBGuest.used == False)
    
    # Filter by search query if provided
    if q:
        stmt = stmt.where(DBGuest.name.ilike(f"%{q}%"))
    
    stmt = stmt.order_by(DBGuest.name)
    result = await db.execute(stmt)
    guests = result.scalars().all()
    return guests


@router.post("/guests")
async def create_guest(
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_manager_or_admin)
):
    """Create a new guest for temporary employee creation"""
    try:
        if "name" not in payload or not payload["name"].strip():
            raise HTTPException(
                status_code=400,
                detail="Pole 'name' jest wymagane"
            )
        
        guest = DBGuest(
            name=payload["name"].strip(),
            rfid=payload.get("rfid", "").strip() or None
        )
        db.add(guest)
        await db.commit()
        await db.refresh(guest)
        return guest
        
    except IntegrityError as e:
        await db.rollback()
        if "unique constraint" in str(e).lower():
            raise HTTPException(
                status_code=400,
                detail="Gość z tymi danymi już istnieje"
            )
        raise HTTPException(
            status_code=400,
            detail="Błąd bazy danych: dane są nieprawidłowe"
        )
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Wewnętrzny błąd serwera"
        )

@router.put("/guests/{guest_id:int}")
async def update_guest(
    guest_id: int,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_manager_or_admin)
):
    """Update a guest's name or RFID"""
    try:
        result = await db.execute(
            select(DBGuest).where(DBGuest.id == guest_id)
        )
        guest = result.scalar_one_or_none()

        if not guest:
            raise HTTPException(status_code=404, detail="Gość nie znaleziony")

        if "name" in payload and payload["name"].strip():
            guest.name = payload["name"].strip()

        if "rfid" in payload:
            new_rfid = payload["rfid"].strip() or None
            if new_rfid != guest.rfid:
                # Check if new RFID is already used by another guest
                rfid_result = await db.execute(
                    select(DBGuest).where(
                        DBGuest.rfid == new_rfid,
                        DBGuest.id != guest_id
                    )
                )
                existing_guest = rfid_result.scalar_one_or_none()
                if existing_guest:
                    raise HTTPException(
                        status_code=400,
                        detail="Inny gość z tym RFID już istnieje"
                    )
                guest.rfid = new_rfid

        await db.commit()
        await db.refresh(guest)
        return guest
        
    except IntegrityError as e:
        await db.rollback()
        if "unique constraint" in str(e).lower():
            raise HTTPException(
                status_code=400,
                detail="Gość z tymi danymi już istnieje"
            )
        raise HTTPException(
            status_code=400,
            detail="Błąd bazy danych: dane są nieprawidłowe"
        )
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Wewnętrzny błąd serwera"
        )

@router.get("/guests/{guest_id:int}")
async def get_guest(
    guest_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_manager_or_admin)
):
    """Get a guest by ID"""
    result = await db.execute(
        select(DBGuest).where(DBGuest.id == guest_id)
    )
    guest = result.scalar_one_or_none()

    if not guest:
        raise HTTPException(status_code=404, detail="Gość nie znaleziony")

    return guest

@router.delete("/guests/{guest_id:int}")
async def delete_guest(
    guest_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_manager_or_admin)
):
    """Delete a guest"""
    try:
        result = await db.execute(
            select(DBGuest).where(DBGuest.id == guest_id)
        )
        guest = result.scalar_one_or_none()

        if not guest:
            raise HTTPException(status_code=404, detail="Gość nie znaleziony")

        if guest.used:
            raise HTTPException(status_code=400, detail="Nie można usunąć gościa, który został już użyty")

        await db.delete(guest)
        await db.commit()
        return {"message": "Gość został usunięty"}

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Wewnętrzny błąd serwera"
        )

@router.post("/temporary-employees")
async def create_temporary_employee(
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_manager_or_admin)
):
    """Create a temporary employee from a guest"""
    from models.db_guest import DBGuest
    
    try:
        # Validate required fields
        required_fields = ["guest_id", "first_name", "last_name", "company"]
        for field in required_fields:
            if field not in payload or not payload[field]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Pole '{field}' jest wymagane"
                )
        
        # Get the guest
        result = await db.execute(
            select(DBGuest).where(DBGuest.id == payload["guest_id"])
        )
        guest = result.scalar_one_or_none()
        
        if not guest:
            raise HTTPException(
                status_code=404,
                detail="Gość nie znaleziony"
            )
        
        if guest.used:
            raise HTTPException(
                status_code=400,
                detail="Gość został już użyty"
            )
        
        # Create employee with RFID from guest
        employee = EmployeeDB(
            first_name=payload["first_name"].strip(),
            last_name=payload["last_name"].strip(),
            company=payload["company"].strip(),
            rfid=guest.rfid,
            wms_login=payload.get("wms_login", "").strip(),
            site_id=await resolve_site_id(db, payload)
        )
        
        # Mark guest as used
        guest.used = True
        
        db.add(employee)
        db.add(guest)
        await db.commit()
        await db.refresh(employee)
        
        return {
            "employee": employee,
            "message": "Pracownik tymczasowy został utworzony ✅"
        }
        
    except IntegrityError as e:
        await db.rollback()
        if "unique constraint" in str(e).lower():
            raise HTTPException(
                status_code=400,
                detail="Pracownik z tymi danymi już istnieje"
            )
        raise HTTPException(
            status_code=400,
            detail="Błąd bazy danych: dane są nieprawidłowe"
        )
    except HTTPException:
        await db.rollback()
        raise
    except ValueError as e:
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Błąd walidacji: {str(e)}"
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Wewnętrzny błąd serwera"
        )


# ===============================
# DEVICES
# ===============================

@router.post("/devices")
async def create_device(
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    try:
        # Validate required fields
        required_fields = ["name", "type", "serial_number", "rfid", "site"]
        for field in required_fields:
            if field not in payload or not payload[field]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Pole '{field}' jest wymagane"
                )
        
        # Validate device type
        try:
            device_type = DeviceType(payload["type"])
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Typ urządzenia musi być 'scanner' lub 'printer'"
            )
        
        # Site з довідника (за назвою або site_id)
        site_id = await resolve_site_id(db, payload)
        
        # Coerce status_id: empty string / null -> None; non-numeric -> clear 400
        raw_status = payload.get("status_id")
        if raw_status in (None, "", "null"):
            status_id = None
        else:
            try:
                status_id = int(raw_status)
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=400,
                    detail="Nieprawidłowy status urządzenia"
                )

        device = DeviceDB(
            name=payload["name"].upper().strip(),
            type=device_type,
            serial_number=payload["serial_number"].strip(),
            rfid=payload["rfid"].strip(),
            site_id=site_id,
            ip=(payload.get("ip") or "").strip() or None,
            enabled=bool(payload.get("enabled", True)),
            status_id=status_id
        )

        db.add(device)
        await db.commit()
        await db.refresh(device)
        return device
        
    except IntegrityError as e:
        await db.rollback()
        error_str = str(e).lower()
        # check the specific constraints first — every unique violation contains
        # the text "unique constraint", so it must NOT be used as a catch-all
        if "devices_name_key" in error_str:
            raise HTTPException(
                status_code=400,
                detail=f"Urządzenie o nazwie '{payload.get('name', '').upper()}' już istnieje"
            )
        elif "devices_serial_number_key" in error_str:
            raise HTTPException(
                status_code=400,
                detail="Urządzenie z tym numerem seryjnym już istnieje"
            )
        elif "ix_devices_rfid" in error_str or "devices_rfid_key" in error_str:
            raise HTTPException(
                status_code=400,
                detail="Urządzenie z tym RFID już istnieje"
            )
        elif "uq_devices_ip" in error_str:
            raise HTTPException(
                status_code=400,
                detail=f"Urządzenie z adresem IP '{payload.get('ip', '')}' już istnieje"
            )
        raise HTTPException(
            status_code=400,
            detail="Błąd bazy danych: dane są nieprawidłowe"
        )
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception("Device creation failed for payload: %s", payload)
        raise HTTPException(
            status_code=500,
            detail="Wewnętrzny błąd serwera"
        )



@router.get("/devices")
async def get_devices(
    q: str | None = Query(default=None),
    status_ids: list[int] | None = Query(default=None),
    assigned: str | None = Query(
        default=None,
        description="'assigned' = tylko wydane, 'unassigned' = tylko wolne, brak = wszystkie",
    ),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    stmt = (
        select(DeviceDB)
        .options(
            selectinload(DeviceDB.employee),
            selectinload(DeviceDB.ports),
            selectinload(DeviceDB.status),
            selectinload(DeviceDB.site)
        )
    )

    if q:
        stmt = stmt.where(
            or_(
                DeviceDB.name.ilike(f"%{q}%"),
                DeviceDB.serial_number.ilike(f"%{q}%"),
                DeviceDB.rfid.ilike(f"%{q}%")
            )
        )

    if status_ids:
        stmt = stmt.where(
            DeviceDB.status_id.in_(status_ids)
        )

    # Kolumna "Przypisany do": pozwala odrzucić puste wiersze i wrócić do nich.
    if assigned == "assigned":
        stmt = stmt.where(DeviceDB.employee_id.isnot(None))
    elif assigned == "unassigned":
        stmt = stmt.where(DeviceDB.employee_id.is_(None))

    stmt = stmt.order_by(DeviceDB.name)

    result = await db.execute(stmt)
    devices = result.scalars().all()

    return [
        {
            "id": d.id,
            "name": d.name,
            "rfid": d.rfid,
            "serial_number": d.serial_number,
            "type": d.type.value,
            "site": d.site.name if d.site else None,
            "site_id": d.site_id,
            "ip": d.ip,
            "enabled": d.enabled,

            "status_id": d.status_id,
            "status_name": d.status.name if d.status else None,

            "ports": [
                {
                    "id": p.id,
                    "port_number": p.port_number
                }
                for p in d.ports
            ],

            "employee_wms_login":
                d.employee.wms_login if d.employee else None
        }
        for d in devices
    ]


@router.get("/devices/{device_id:int}")
async def get_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    result = await db.execute(
        select(DeviceDB)
        .where(DeviceDB.id == device_id)
        .options(
            selectinload(DeviceDB.ports),
            selectinload(DeviceDB.status),
            selectinload(DeviceDB.site)
        )
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    return {
        "id": device.id,
        "name": device.name,
        "rfid": device.rfid,
        "serial_number": device.serial_number,
        "type": device.type.value,
        "site": device.site.name if device.site else None,
        "site_id": device.site_id,
        "ip": device.ip,
        "enabled": device.enabled,
        "status_id": device.status_id,
        "status_name": device.status.name if device.status else None,
        "ports": [{"id": p.id, "port_number": p.port_number} for p in device.ports]
    }

@router.put("/devices/{device_id:int}")
async def update_device(
    device_id: int,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):

    try:

        result = await db.execute(
            select(DeviceDB)
            .options(
                selectinload(DeviceDB.status),
                selectinload(DeviceDB.ports)
            )
            .where(DeviceDB.id == device_id)
        )

        device = result.scalar_one_or_none()

        if not device:
            raise HTTPException(
                status_code=404,
                detail="Urządzenie nie znalezione"
            )

        changes = {}

        editable_fields = [
            "name",
            "serial_number",
            "rfid",
            "type",
            "site_id",
            "ip",
            "enabled",
            "status_id"
        ]

        # site приходить назвою (адмінка, синхронізація з Google Sheets) —
        # переводимо в site_id, щоб далі працювала спільна логіка порівняння
        if "site" in payload or "site_id" in payload:
            payload["site_id"] = await resolve_site_id(db, payload)

        for field in editable_fields:

            if field not in payload:
                continue

            new_value = payload[field]

            if field == "type":
                new_value = DeviceType(new_value)
            
            if field == "name" and new_value:
                new_value = new_value.upper().strip()

            if field in ["serial_number", "rfid"] and new_value:
                new_value = str(new_value).strip()

            if field == "ip":
                new_value = (
                    str(new_value).strip()
                    if new_value
                    else None
                )

            old_value = getattr(device, field)

            if old_value != new_value:

                changes[field] = {
                    "old": old_value,
                    "new": new_value
                }

                setattr(device, field, new_value)

        # Handle ports separately
        port_changes = []
        if "ports" in payload:
            new_port_numbers = set(str(p).strip() for p in payload["ports"] if str(p).strip())
            existing_port_numbers = set(p.port_number for p in device.ports)
            
            # Find ports to remove
            ports_to_remove = existing_port_numbers - new_port_numbers
            # Find ports to add
            ports_to_add = new_port_numbers - existing_port_numbers
            
            # Remove ports
            for port in list(device.ports):
                if port.port_number in ports_to_remove:
                    await db.delete(port)
                    port_changes.append(f"removed {port.port_number}")
            
            # Add ports with error handling
            try:
                for port_number in ports_to_add:
                    new_port = DevicePortDB(port_number=port_number, device_id=device.id)
                    db.add(new_port)
                    port_changes.append(f"added {port_number}")
                # Try to flush to catch unique constraint errors early
                await db.flush()
            except IntegrityError as e:
                await db.rollback()
                if "unique constraint" in str(e).lower():
                    raise HTTPException(
                        status_code=400,
                        detail=f"Port {port_number} jest już używany w innym urządzeniu"
                    )
                raise

        await db.commit()
        await db.refresh(device)
        
        if changes or port_changes:

            descriptions = await build_change_descriptions(
                db=db,
                device=device,
                changes=changes
            )
            
            if port_changes:
                descriptions.append(f"changed device ports {' and '.join(port_changes)}")

            await create_device_transaction(
                db=db,
                user_id=user["id"],
                device=device,
                descriptions=descriptions,
                note=payload.get("notes")
            )
            # Персистимо аудит-транзакцію: flush недостатньо — без цього commit
            # рядок відкочується на закритті сесії (регресія з d9fd662).
            await db.commit()

        return device

    except IntegrityError as e:

        await db.rollback()

        error_str = str(e).lower()

        if "devices_name_key" in error_str:
            raise HTTPException(
                status_code=400,
                detail="Urządzenie z tą nazwą już istnieje"
            )

        if "devices_serial_number_key" in error_str:
            raise HTTPException(
                status_code=400,
                detail="Numer seryjny już istnieje"
            )

        if "devices_rfid_key" in error_str:
            raise HTTPException(
                status_code=400,
                detail="RFID już istnieje"
            )

        raise HTTPException(
            status_code=400,
            detail="Błąd bazy danych"
        )


@router.delete("/devices/{device_id:int}")
async def delete_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    result = await db.execute(
        select(DeviceDB).where(DeviceDB.id == device_id)
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    await db.delete(device)
    await db.commit()


@router.post("/devices/{device_id:int}/unassign")
async def unassign_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    """Zdjęcie sprzętu z pracownika bez czytnika.

    Normalnie zwrot robi sam pracownik kartą, a manager go autoryzuje. Zostaje
    reszta przypadków: ktoś odszedł z pracy, zgubił kartę albo urządzenie wróciło
    pocztą — wtedy nikt tego nie zamknie i sprzęt wisi na kimś w nieskończoność.
    Stąd ten przycisk.

    Wiersz w historii powstaje taki sam jak przy zwrocie na czytniku, bo dla
    magazynu to jest ten sam fakt. Różnicę niesie kolumna source: nikt tu nie
    przykładał karty, więc w miejscu pracownika ekran pokaże administratora,
    który zwrot wykonał.
    """
    device = (await db.execute(
        select(DeviceDB)
        .where(DeviceDB.id == device_id)
        .options(selectinload(DeviceDB.employee))
    )).scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="Nie ma takiego urządzenia")

    if device.employee_id is None:
        raise HTTPException(
            status_code=400,
            detail=f"{device.name} nie jest do nikogo przypisany"
        )

    # Kogo zdejmujemy — do odpowiedzi, żeby ekran mógł to pokazać. Sam wiersz
    # historii pracownika nie zapisuje, tak samo jak zwrot na czytniku.
    previous = device.employee
    previous_label = previous.wms_login if previous else None

    device.employee_id = None

    db.add(TransactionDB(
        type=TransactionType.unregistered,
        device_id=device.id,
        employee_id=None,
        manager_id=user["id"],
        source=TRANSACTION_SOURCE_PANEL,
    ))

    await db.commit()

    logger.info(
        "Admin %s zdjął %s z %s z panelu",
        user["username"], device.name, previous_label
    )

    return {
        "device": device.name,
        "previous_employee": previous_label,
        "performed_by": user["username"],
    }


# ===============================
# DEVICE PORTS
# ===============================

@router.post("/devices/{device_id:int}/ports")
async def create_device_port(
    device_id: int,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):

    result = await db.execute(
        select(DeviceDB)
        .options(selectinload(DeviceDB.ports))
        .where(DeviceDB.id == device_id)
    )

    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=404,
            detail="Urządzenie nie znalezione"
        )

    if not payload.get("port_number"):
        raise HTTPException(
            status_code=400,
            detail="port_number required"
        )

    try:
        port = DevicePortDB(
            port_number=str(payload["port_number"]).strip(),
            device_id=device.id
        )

        db.add(port)
        await db.flush()

        descriptions = [
            f"changed device ports added {port.port_number}"
        ]

        await create_device_transaction(
            db=db,
            user_id=user["id"],
            device=device,
            descriptions=descriptions
        )

        await db.commit()
        await db.refresh(port)

        return port
    
    except IntegrityError as e:
        await db.rollback()
        if "unique constraint" in str(e).lower():
            raise HTTPException(
                status_code=400,
                detail=f"Port {payload['port_number']} jest już używany w innym urządzeniu"
            )
        raise HTTPException(
            status_code=400,
            detail="Błąd bazy danych"
        )


@router.delete("/devices/{device_id:int}/ports/{port_id:int}")
async def delete_device_port(
    device_id: int,
    port_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):

    result = await db.execute(
        select(DeviceDB)
        .options(selectinload(DeviceDB.ports))
        .where(DeviceDB.id == device_id)
    )

    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=404,
            detail="Urządzenie nie znalezione"
        )

    result = await db.execute(
        select(DevicePortDB).where(
            DevicePortDB.id == port_id,
            DevicePortDB.device_id == device_id
        )
    )

    port = result.scalar_one_or_none()

    if not port:
        raise HTTPException(
            status_code=404,
            detail="Port nie znaleziony"
        )

    descriptions = [
        f"changed device ports removed {port.port_number}"
    ]

    await create_device_transaction(
        db=db,
        user_id=user["id"],
        device=device,
        descriptions=descriptions
    )

    await db.delete(port)
    await db.commit()

    return {
        "message": "Port deleted"
    }


# ===============================
# DEPARTMENT MANAGERS
# ===============================
@router.post("/department-managers")
async def create_department_manager(
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    try:
        # Validate required fields
        required_fields = ["department", "email"]
        for field in required_fields:
            if field not in payload or not payload[field]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Pole '{field}' jest wymagane"
                )
        
        manager = DepartmentManagerDB(
            department=payload["department"].strip(),
            email=payload["email"].strip()
        )
        db.add(manager)
        await db.commit()
        await db.refresh(manager)
        return manager
        
    except IntegrityError as e:
        await db.rollback()
        if "unique constraint" in str(e).lower():
            raise HTTPException(
                status_code=400,
                detail="Kierownik departamentu z tymi danymi już istnieje"
            )
        raise HTTPException(
            status_code=400,
            detail="Błąd bazy danych: dane są nieprawidłowe"
        )
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Wewnętrzny błąd serwera"
        )

@router.get("/department-managers")
async def get_department_managers(
    q: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    stmt = select(DepartmentManagerDB)
    if q:
        stmt = stmt.where(DepartmentManagerDB.department.ilike(f"%{q}%"))
    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/department-managers/{manager_id:int}")
async def get_department_manager(
    manager_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    manager = await db.get(DepartmentManagerDB, manager_id)
    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")
    return manager

@router.put("/department-managers/{manager_id:int}")
async def update_department_manager(
    manager_id: int,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    try:
        manager = await db.get(DepartmentManagerDB, manager_id)
        if not manager:
            raise HTTPException(status_code=404, detail="Kierownik departamentu nie znaleziony")
        
        for field in ["department", "email"]:
            if field in payload:
                value = payload[field]
                if isinstance(value, str):
                    value = value.strip()
                setattr(manager, field, value)
        
        await db.commit()
        await db.refresh(manager)
        return manager
        
    except IntegrityError as e:
        await db.rollback()
        if "unique constraint" in str(e).lower():
            raise HTTPException(
                status_code=400,
                detail="Kierownik departamentu z tymi danymi już istnieje"
            )
        raise HTTPException(
            status_code=400,
            detail="Błąd bazy danych: dane są nieprawidłowe"
        )
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Wewnętrzny błąd serwera"
        )

@router.delete("/department-managers/{manager_id:int}")
async def delete_department_manager(
    manager_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    manager = await db.get(DepartmentManagerDB, manager_id)
    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")
    await db.delete(manager)
    await db.commit()
    return

#================================
# Dashboard report
#================================
# Magazyn stoi w Polsce, a sesja bazy pracuje w UTC — bez tej zamiany
# "ostatnie wypożyczenie" pokazywałoby godzinę sprzed dwóch.
DASHBOARD_TZ = ZoneInfo("Europe/Warsaw")


def _as_local_stamp(moment) -> str | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(DASHBOARD_TZ).strftime("%Y-%m-%d %H:%M")


@router.get("/dashboard")
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_dashboard_viewer)
):
    # =========================
    # GLOBAL COUNTS
    # =========================
    available_stmt = select(func.count()).select_from(DeviceDB).where(DeviceDB.enabled == True)
    disabled_stmt = select(func.count()).select_from(DeviceDB).where(DeviceDB.enabled == False)

    available = (await db.execute(available_stmt)).scalar() or 0
    disabled = (await db.execute(disabled_stmt)).scalar() or 0

    # =========================
    # BY TYPE (ENABLED)
    # =========================
    type_stmt = (
        select(
            DeviceDB.type,
            func.count()
        )
        .where(DeviceDB.enabled == True)
        .group_by(DeviceDB.type)
    )

    type_result = await db.execute(type_stmt)

    types = {
        "scanner": 0,
        "printer": 0
    }

    for t, count in type_result:
        types[t.value] = count

    # =========================
    # BY TYPE (DISABLED)
    # =========================
    disabled_type_stmt = (
        select(
            DeviceDB.type,
            func.count()
        )
        .where(DeviceDB.enabled == False)
        .group_by(DeviceDB.type)
    )

    disabled_type_result = await db.execute(disabled_type_stmt)

    disabled_types = {
        "scanner": 0,
        "printer": 0
    }

    for t, count in disabled_type_result:
        disabled_types[t.value] = count

    # =========================
    # WYDANE / WOLNE (per typ)
    # =========================
    # "Wydane" to sprzęt z przypisanym loginem — bez względu na dostępność,
    # bo fizycznie jest u człowieka nawet wtedy, gdy w systemie go zablokowano.
    # "Wolne" liczy tylko dostępne: zablokowany sprzęt leżący w szafie nie jest
    # tym, po co ktoś przyjdzie. Te dwie kolumny nie muszą więc sumować się do
    # kolumny "Dostępne" i świadomie tak zostają.
    assigned_stmt = (
        select(DeviceDB.type, func.count())
        .where(DeviceDB.employee_id.is_not(None))
        .group_by(DeviceDB.type)
    )
    free_stmt = (
        select(DeviceDB.type, func.count())
        .where(DeviceDB.employee_id.is_(None), DeviceDB.enabled == True)
        .group_by(DeviceDB.type)
    )

    assigned_types = {"scanner": 0, "printer": 0}
    for t, count in (await db.execute(assigned_stmt)):
        assigned_types[t.value] = count

    free_types = {"scanner": 0, "printer": 0}
    for t, count in (await db.execute(free_stmt)):
        free_types[t.value] = count

    # =========================
    # UŻYCIE PER SITE
    # =========================
    site_usage_stmt = (
        select(
            SiteDB.name.label("site"),

            func.count(func.distinct(EmployeeDB.id)).label("employees"),
            func.count(DeviceDB.id).label("devices"),

            func.count().filter(DeviceDB.type == DeviceType.scanner).label("scanners"),
            func.count().filter(DeviceDB.type == DeviceType.printer).label("printers"),
        )
        .join(DeviceDB, DeviceDB.employee_id == EmployeeDB.id)
        .outerjoin(SiteDB, SiteDB.id == EmployeeDB.site_id)
        .where(
            DeviceDB.enabled == True,
            DeviceDB.employee_id.is_not(None)
        )
        .group_by(SiteDB.name)
    )

    site_usage_result = await db.execute(site_usage_stmt)


    sites_usage = [
        {
            "site": row.site or "Brak",

            # Etykieta wyżej jest dla oka ("Brak" zamiast pustego); rozwinięcie
            # potrzebuje wartości, którą da się odesłać do API — pusty ciąg
            # oznacza tam właśnie pracowników bez site.
            "site_filter": row.site or "",

            "employees": row.employees or 0,
            "devices": row.devices or 0,
            "scanners": row.scanners or 0,
            "printers": row.printers or 0,
        }
        for row in site_usage_result
    ]

    return {
        "devices": {
            "available": available,
            "disabled": disabled,
            "by_type": types,
            "disabled_by_type": disabled_types,
            "assigned_by_type": assigned_types,
            "free_by_type": free_types
        },
        "sites": sites_usage
    }

# ===============================
# Dashboard drill-down
# ===============================
# Kafelki wyżej pokazują same liczby. Poniższe dwa endpointy zwracają wiersze,
# które się na daną liczbę składają — czyli kto trzyma jaki sprzęt. Filtry
# muszą odpowiadać dokładnie tym z get_dashboard: inaczej rozwinięcie nie
# zgadzałoby się z liczbą, spod której je otwarto.


async def _last_rentals(db: AsyncSession, column) -> dict[int, str]:
    """Ostatnia rejestracja w rozbiciu na urządzenia albo na pracowników.

    Jedno zapytanie na całe rozwinięcie, nie jedno na wiersz — inaczej otwarcie
    listy stu urządzeń to sto zapytań do bazy.
    """
    stmt = (
        select(column, func.max(TransactionDB.timestamp))
        .where(TransactionDB.type == TransactionType.registered)
        .group_by(column)
    )
    return {
        key: _as_local_stamp(moment)
        for key, moment in (await db.execute(stmt))
        if key is not None
    }


def _dashboard_device_row(device: DeviceDB, last_rental: dict[int, str]) -> dict:
    """Urządzenie razem z osobą, która je ma."""
    employee = device.employee
    return {
        # Kiedy ten sprzęt ostatnio komuś wydano. Dla wolnego to data poprzedniego
        # wypożyczenia, nie zwrotu — pytanie brzmi "kiedy ostatnio pracował".
        "last_rental": last_rental.get(device.id),
        "id": device.id,
        "name": device.name,
        "serial_number": device.serial_number,
        "rfid": device.rfid,
        "type": device.type.value,
        "enabled": device.enabled,
        "site": device.site.name if device.site else None,
        "status_name": device.status.name if device.status else None,
        "employee": {
            "id": employee.id,
            "wms_login": employee.wms_login,
            "first_name": employee.first_name,
            "last_name": employee.last_name,
            "site": employee.site.name if employee.site else None,
        } if employee else None,
    }


@router.get("/dashboard/devices")
async def get_dashboard_devices(
    device_type: str | None = Query(
        default=None, alias="type", description="'scanner' albo 'printer'; brak = oba typy"
    ),
    enabled: bool | None = Query(default=None, description="brak = i dostępne, i niedostępne"),
    assigned: bool | None = Query(default=None, description="true = tylko wydane, false = tylko wolne"),
    site: str | None = Query(
        default=None,
        description="Site posiadacza. Pominięty = bez filtra, pusty = pracownicy bez site ('Brak')",
    ),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_dashboard_viewer)
):
    """Urządzenia stojące za liczbą klikniętą na dashboardzie."""
    if device_type not in (None, "scanner", "printer"):
        raise HTTPException(status_code=400, detail="type musi być 'scanner' albo 'printer'")

    stmt = (
        select(DeviceDB)
        .outerjoin(EmployeeDB, DeviceDB.employee_id == EmployeeDB.id)
        .options(
            selectinload(DeviceDB.employee).selectinload(EmployeeDB.site),
            selectinload(DeviceDB.status),
            selectinload(DeviceDB.site)
        )
    )

    if device_type:
        stmt = stmt.where(DeviceDB.type == DeviceType(device_type))

    if enabled is not None:
        stmt = stmt.where(DeviceDB.enabled.is_(enabled))

    if assigned is not None:
        stmt = stmt.where(
            DeviceDB.employee_id.is_not(None) if assigned else DeviceDB.employee_id.is_(None)
        )

    if site is not None:
        # Pusty ciąg to wiersz "Brak" z tabeli per site: pracownik istnieje,
        # ale site nie ma. Samo site_id IS NULL złapałoby przy outerjoin także
        # urządzenia bez posiadacza — stąd dodatkowy warunek na EmployeeDB.id.
        stmt = stmt.where(EmployeeDB.id.is_not(None))
        stmt = (
            stmt.where(EmployeeDB.site_id.is_(None))
            if site == ""
            else stmt.join(SiteDB, SiteDB.id == EmployeeDB.site_id).where(SiteDB.name == site)
        )

    # Alfabetycznie po nazwie urządzenia — tak się tej listy szuka wzrokiem.
    # Wcześniej rządziło nazwisko posiadacza i nazwy szły pozornie losowo.
    stmt = stmt.order_by(DeviceDB.name)

    devices = (await db.execute(stmt)).scalars().all()
    last_rental = await _last_rentals(db, TransactionDB.device_id)

    return [_dashboard_device_row(d, last_rental) for d in devices]


@router.get("/dashboard/employees")
async def get_dashboard_employees(
    site: str | None = Query(
        default=None,
        description="Site. Pominięty = bez filtra, pusty = pracownicy bez site ('Brak')",
    ),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_dashboard_viewer)
):
    """Pracownicy stojący za kolumną "Pracownicy" w tabeli per dział — czyli ci,
    którzy mają wydane co najmniej jedno dostępne urządzenie."""
    stmt = (
        select(EmployeeDB)
        .join(DeviceDB, DeviceDB.employee_id == EmployeeDB.id)
        .where(DeviceDB.enabled.is_(True))
        .options(
            selectinload(EmployeeDB.devices).selectinload(DeviceDB.status),
            selectinload(EmployeeDB.devices).selectinload(DeviceDB.site),
            selectinload(EmployeeDB.site)
        )
        .distinct()
        .order_by(EmployeeDB.wms_login)
    )

    if site is not None:
        stmt = (
            stmt.where(EmployeeDB.site_id.is_(None))
            if site == ""
            else stmt.join(SiteDB, SiteDB.id == EmployeeDB.site_id).where(SiteDB.name == site)
        )

    employees = (await db.execute(stmt)).scalars().all()
    last_rental = await _last_rentals(db, TransactionDB.employee_id)

    return [
        {
            "id": e.id,
            "wms_login": e.wms_login,
            # Kiedy ta osoba ostatnio coś pobrała.
            "last_rental": last_rental.get(e.id),
            "first_name": e.first_name,
            "last_name": e.last_name,
            "company": e.company,
            "site": e.site.name if e.site else None,

            # Cały sprzęt przypisany do osoby, także niedostępny — fizycznie
            # nadal jest u niej. Liczba na dashboardzie liczy tylko dostępne,
            # więc ta lista bywa od niej dłuższa; stąd flaga "enabled".
            "devices": [
                {
                    "id": d.id,
                    "name": d.name,
                    "type": d.type.value,
                    "serial_number": d.serial_number,
                    "enabled": d.enabled,
                    "status_name": d.status.name if d.status else None,
                    "site": d.site.name if d.site else None,
                }
                for d in sorted(e.devices, key=lambda d: d.name)
            ],
        }
        for e in employees
    ]
