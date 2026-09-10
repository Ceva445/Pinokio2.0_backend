"""Тести зняття сприяту з працівника з панелі адміністратора.

Фізичне повернення робить сам працівник карткою. Кнопка в панелі — на решту
випадків: людина звільнилась, загубила картку, пристрій приїхав поштою. Тому
запис в історії має бути таким самим «Wyrejestrowanie (zwrot)», але підписаним
адміном, який його зробив.

Ключове, що перевіряється: новий рядок не змішується зі старими. Історія
повернень на зчитувачі теж не має працівника і теж має менеджера — відрізняє їх
лише колонка source.
"""
import inspect

import pytest
from fastapi import HTTPException

from app.dependencies.admin import require_admin
from models.db_device import DeviceDB, DeviceType
from models.db_employee import EmployeeDB
from models.db_transaction import (
    TRANSACTION_SOURCE_PANEL,
    TransactionDB,
    TransactionType,
)
from models.db_user import UserDB, UserRole
from routers.admin.api import unassign_device
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def warehouse(db_session):
    admin = UserDB(first_name="Local", last_name="Admin", username="C-ADMIN",
                   password_hash="x", role=UserRole.admin)
    anna = EmployeeDB(last_name="Nowak", first_name="Anna", rfid="r-anna",
                      company="Demo", wms_login="A-NOWAK", department="STOCK")
    db_session.add_all([admin, anna])
    await db_session.commit()

    held = DeviceDB(name="TERM161", rfid="r-161", serial_number="sn-161",
                    type=DeviceType.scanner, employee_id=anna.id)
    free = DeviceDB(name="TERM162", rfid="r-162", serial_number="sn-162",
                    type=DeviceType.scanner)
    db_session.add_all([held, free])
    await db_session.commit()

    return {
        "admin": {"id": admin.id, "username": admin.username, "role": "admin"},
        "anna": anna,
        "held": held,
        "free": free,
    }


async def _transactions(db) -> list[TransactionDB]:
    return list((await db.execute(select(TransactionDB))).scalars().all())


# ---------------------------------------------------------------------------
# Сам зняття
# ---------------------------------------------------------------------------
async def test_device_comes_off_the_employee(db_session, warehouse):
    result = await unassign_device(
        device_id=warehouse["held"].id, db=db_session, user=warehouse["admin"]
    )

    await db_session.refresh(warehouse["held"])
    assert warehouse["held"].employee_id is None
    assert result["device"] == "TERM161"
    assert result["previous_employee"] == "A-NOWAK"
    assert result["performed_by"] == "C-ADMIN"


async def test_history_gets_an_ordinary_return(db_session, warehouse):
    """Для складу це той самий факт, що й повернення на зчитувачі."""
    await unassign_device(
        device_id=warehouse["held"].id, db=db_session, user=warehouse["admin"]
    )

    transactions = await _transactions(db_session)
    assert len(transactions) == 1

    tx = transactions[0]
    assert tx.type == TransactionType.unregistered
    assert tx.device_id == warehouse["held"].id
    assert tx.employee_id is None


async def test_the_row_is_signed_by_the_admin(db_session, warehouse):
    await unassign_device(
        device_id=warehouse["held"].id, db=db_session, user=warehouse["admin"]
    )

    tx = (await _transactions(db_session))[0]
    assert tx.manager_id == warehouse["admin"]["id"]
    assert tx.source == TRANSACTION_SOURCE_PANEL


async def test_reader_returns_stay_unmarked(db_session, warehouse):
    """Найважливіше: стара історія не має виглядати як зняте з панелі.

    Повернення на зчитувачі теж без працівника і теж з менеджером — якби екран
    розрізняв їх по ролі підписанта, 49 наявних рядків на проді раптом почали б
    показувати адміна в колонці працівника."""
    db_session.add(TransactionDB(
        type=TransactionType.unregistered,
        device_id=warehouse["free"].id,
        employee_id=None,
        manager_id=warehouse["admin"]["id"],
    ))
    await db_session.commit()

    reader_row = (await _transactions(db_session))[0]
    assert reader_row.source is None


# ---------------------------------------------------------------------------
# Чого робити не можна
# ---------------------------------------------------------------------------
async def test_free_device_is_refused(db_session, warehouse):
    with pytest.raises(HTTPException) as exc:
        await unassign_device(
            device_id=warehouse["free"].id, db=db_session, user=warehouse["admin"]
        )

    assert exc.value.status_code == 400
    assert "TERM162" in exc.value.detail
    assert not await _transactions(db_session)


async def test_unknown_device_is_refused(db_session, warehouse):
    with pytest.raises(HTTPException) as exc:
        await unassign_device(device_id=9999, db=db_session, user=warehouse["admin"])

    assert exc.value.status_code == 404


async def test_only_admin_may_take_equipment_back():
    """Kierownik ma swój ekran urządzeń tylko do podglądu — ta akcja jest poza."""
    guard = inspect.signature(unassign_device).parameters["user"].default.dependency
    assert guard is require_admin
