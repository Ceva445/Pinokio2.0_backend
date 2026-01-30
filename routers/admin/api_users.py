from fastapi import APIRouter, Depends, Body, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from db.session import get_db
from app.dependencies.admin import require_admin
from models.db_user import UserDB, UserRole
from schemas.user import UserCreate, UserUpdate
from managers.auth_manager import auth_manager

router = APIRouter(
    prefix="/admin/api",
    tags=["Admin Users API"]
)

# ===============================
# LIST + SEARCH
# ===============================

@router.get("/users")
async def list_users(
    q: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    stmt = select(UserDB)

    if q:
        stmt = stmt.where(
            or_(
                UserDB.username.ilike(f"%{q}%"),
                UserDB.first_name.ilike(f"%{q}%"),
                UserDB.last_name.ilike(f"%{q}%")
            )
        )

    result = await db.execute(stmt)
    return result.scalars().all()

# ===============================
# GET BY ID
# ===============================

@router.get("/users/{user_id:int}")
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    result = await db.execute(
        select(UserDB).where(UserDB.id == user_id)
    )
    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(404, "User not found")

    return db_user

# ===============================
# CREATE
# ===============================

@router.post("/users")
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    hashed = auth_manager.get_password_hash(payload.password)

    db_user = UserDB(
        first_name=payload.first_name,
        last_name=payload.last_name,
        username=payload.username,
        password_hash=hashed,
        role=payload.role,
        is_active=True
    )

    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user

# ===============================
# UPDATE
# ===============================

@router.put("/users/{user_id:int}")
async def update_user(
    user_id: int,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    result = await db.execute(
        select(UserDB).where(UserDB.id == user_id)
    )
    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(404, "User not found")

    if payload.password:
        db_user.password_hash = auth_manager.get_password_hash(payload.password)

    for field in ["first_name", "last_name", "role", "is_active"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(db_user, field, value)

    await db.commit()
    await db.refresh(db_user)
    return db_user

# ===============================
# DELETE
# ===============================

@router.delete("/users/{user_id:int}", status_code=204)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin)
):
    result = await db.execute(
        select(UserDB).where(UserDB.id == user_id)
    )
    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(404, "User not found")

    await db.delete(db_user)
    await db.commit()
