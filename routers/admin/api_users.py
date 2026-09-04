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
    users = result.scalars().all()

    # Kto ma teraz aktywną sesję (sesje trzymane w pamięci procesu).
    # Bez tego panel pokazywał przycisk wylogowania przy każdym managerze,
    # także takim, który wcale nie jest zalogowany.
    from managers.auth_manager import auth_manager
    from app.main import revoked_tokens, esp_watchers

    logged_in_ids = {
        (sess.get("user") or {}).get("id")
        for token, sess in auth_manager.active_sessions.items()
        if token not in revoked_tokens
    }
    bound_by_user = {
        w.get("user_id"): device_id
        for device_id, w in esp_watchers.items()
    }

    return [
        {
            "id": u.id,
            "username": u.username,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "role": u.role.value if hasattr(u.role, "value") else u.role,
            "is_active": u.is_active,
            "must_change_password": u.must_change_password,
            "is_logged_in": u.id in logged_in_ids,
            "bound_device": bound_by_user.get(u.id),
        }
        for u in users
    ]

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
        is_active=True,
        must_change_password=payload.must_change_password
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

    # Nowe hasło od admina zwykle idzie w parze z wymuszeniem zmiany,
    # ale decyduje o tym wyłącznie pole must_change_password z formularza.
    for field in ["first_name", "last_name", "role", "is_active", "must_change_password"]:
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


# ===============================
# FORCE LOGOUT (admin примусово вилоговує менеджера)
# ===============================

@router.post("/users/{user_id:int}/force-logout")
async def force_logout_user(
    user_id: int,
    user=Depends(require_admin),
):
    """Примусовий вилог: revoke усіх токенів користувача, звільнення його ESP,
    розрив його монітор-WS. Наступний запит цього користувача → 401 (на логін)."""
    from app.main import remove_user_from_all_esps, manager, revoked_tokens
    from managers.auth_manager import auth_manager

    revoked = 0
    # 1) revoke токенів із кешу сесій
    for token, sess in list(auth_manager.active_sessions.items()):
        if (sess.get("user") or {}).get("id") == user_id:
            revoked_tokens.add(token)
            auth_manager.remove_session(token)
            revoked += 1

    # 2) звільнити прив'язку ESP (esp_watchers + esp_allowed_users)
    remove_user_from_all_esps(user_id)

    # 3) розірвати монітор-WS цього користувача (+ revoke його токена, якщо є)
    for ws in list(manager.connections.keys()):
        if getattr(ws, "user_id", None) == user_id:
            tok = getattr(ws, "token", None)
            if tok:
                revoked_tokens.add(tok)
                auth_manager.remove_session(tok)
            try:
                await ws.close()
            except Exception:
                pass

    await manager.broadcast_device_list()
    return {"status": "ok", "message": "Menedżer wylogowany", "revoked": revoked}
