from fastapi import APIRouter, Depends, Body, Query, HTTPException
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from models.db_department_manager import DepartmentManagerDB
from models.device_transaction import DeviceChangeTransaction
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, or_

from db.session import get_db
from app.dependencies.admin import require_admin
from models.db_employee import EmployeeDB
from models.db_device import DeviceDB, DeviceType


router = APIRouter(
    prefix="/admin/api",
    tags=["Admin API"]
)

# ===============================
# CREATE
# ===============================

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
            department=payload.get("department", "").strip()
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
    stmt = stmt.order_by(EmployeeDB.last_name, EmployeeDB.first_name)
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

        for field in ["wms_login", "first_name", "last_name", "company", "rfid", "department"]:
            if field in payload:
                value = payload[field]
                if isinstance(value, str):
                    value = value.strip()
                setattr(employee, field, value)

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
        required_fields = ["name", "type", "serial_number", "rfid"]
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
        
        device = DeviceDB(
            name=payload["name"].upper().strip(),
            type=device_type,
            serial_number=payload["serial_number"].strip(),
            rfid=payload["rfid"].strip()
        )

        db.add(device)
        await db.commit()
        await db.refresh(device)
        return device
        
    except IntegrityError as e:
        await db.rollback()
        error_str = str(e).lower()
        if "devices_name_key" in error_str or "unique constraint" in error_str:
            raise HTTPException(
                status_code=400,
                detail=f"Urządzenie o nazwie '{payload.get('name', '').upper()}' już istnieje"
            )
        elif "devices_serial_number_key" in error_str:
            raise HTTPException(
                status_code=400,
                detail="Urządzenie z tym numerem seryjnym już istnieje"
            )
        elif "devices_rfid_key" in error_str:
            raise HTTPException(
                status_code=400,
                detail="Urządzenie z tym RFID już istnieje"
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



@router.get("/devices")
async def get_devices(
    q: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    stmt = (
        select(DeviceDB)
        .options(selectinload(DeviceDB.employee))
    )

    if q:
        stmt = stmt.where(
            or_(
                DeviceDB.name.ilike(f"%{q}%"),
                DeviceDB.serial_number.ilike(f"%{q}%"),
                DeviceDB.rfid.ilike(f"%{q}%")
            )
        )
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
            "enabled": d.enabled,
            "employee_wms_login": d.employee.wms_login if d.employee else None
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
        select(DeviceDB).where(DeviceDB.id == device_id)
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    return device


@router.put("/devices/{device_id:int}")
async def update_device(
    device_id: int,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    try:
        result = await db.execute(
            select(DeviceDB).where(DeviceDB.id == device_id)
        )
        device = result.scalar_one_or_none()

        if not device:
            raise HTTPException(status_code=404, detail="Urządzenie nie znalezione")

        changes = []

        for field in ["name", "serial_number", "rfid", "type", "enabled"]:
            if field in payload:
                try:
                    new_value = (
                        DeviceType(payload[field]) if field == "type" else payload[field]
                    )
                    if field == "name" and new_value:
                        new_value = new_value.upper().strip()
                    elif field in ["serial_number", "rfid"] and new_value:
                        new_value = str(new_value).strip()
                        
                    old_value = getattr(device, field)
                    if old_value != new_value:
                        changes.append(f"{field}: '{old_value}' → '{new_value}'")
                        setattr(device, field, new_value)
                except ValueError as e:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Błąd walidacji dla pola '{field}': {str(e)}"
                    )

        if changes:
            description = "; ".join(changes)
            tx = DeviceChangeTransaction(
                user_id=user["id"],
                device_id=device.id,
                description=description
            )
            db.add(tx)

        await db.commit()
        await db.refresh(device)
        return device
        
    except IntegrityError as e:
        await db.rollback()
        error_str = str(e).lower()
        if "devices_name_key" in error_str:
            raise HTTPException(
                status_code=400,
                detail=f"Urządzenie o nazwie '{payload.get('name', 'UNKNOWN').upper()}' już istnieje"
            )
        elif "devices_serial_number_key" in error_str:
            raise HTTPException(
                status_code=400,
                detail="Urządzenie z tym numerem seryjnym już istnieje"
            )
        elif "devices_rfid_key" in error_str:
            raise HTTPException(
                status_code=400,
                detail="Urządzenie z tym RFID już istnieje"
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
@router.get("/dashboard")
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
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
    # DEPARTMENTS (FULL DATA)
    # =========================
    dept_stmt = (
        select(
            EmployeeDB.department,

            func.count(func.distinct(EmployeeDB.id)).label("employees"),
            func.count(DeviceDB.id).label("devices"),

            func.count().filter(DeviceDB.type == DeviceType.scanner).label("scanners"),
            func.count().filter(DeviceDB.type == DeviceType.printer).label("printers"),
        )
        .join(DeviceDB, DeviceDB.employee_id == EmployeeDB.id)
        .where(
            DeviceDB.enabled == True,
            DeviceDB.employee_id.is_not(None)
        )
        .group_by(EmployeeDB.department)
    )

    dept_result = await db.execute(dept_stmt)

    departments = [
        {
            "department": row.department or "Brak",
            "employees": row.employees or 0,
            "devices": row.devices or 0,
            "scanners": row.scanners or 0,
            "printers": row.printers or 0,
        }
        for row in dept_result
    ]

    return {
        "devices": {
            "available": available,
            "disabled": disabled,
            "by_type": types,
            "disabled_by_type": disabled_types
        },
        "departments": departments
    }