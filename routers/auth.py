"""Маршрути для автентифікації користувачів"""
from fastapi import APIRouter, Depends, HTTPException, status, Form, Request, Response
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import timedelta
from pydantic import BaseModel

from db.session import get_db
from schemas.user import UserCreate, UserOut, Token, UserUpdate
from models.db_user import UserDB, UserRole
from managers.auth_manager import auth_manager

router = APIRouter(prefix="/auth", tags=["Authentication"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def get_token_from_cookie(request: Request) -> str | None:
    return request.cookies.get("access_token")

def get_current_user(required: bool = True):
    async def _get_current_user(
        request: Request,
        token: str = Depends(oauth2_scheme),
        db: AsyncSession = Depends(get_db)
    ):
        token = token or get_token_from_cookie(request)

        # 🔹 Якщо користувач НЕ обовʼязковий і токена немає
        if not token:
            if required:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return None

        # 🔹 Токен «виловлений» (менеджер закрив вкладку → WS-розрив) → недійсний
        from app.main import revoked_tokens
        if token in revoked_tokens:
            if required:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session revoked",
                )
            return None

        # 🔹 Спроба взяти з кешу (але перевіряємо, що JWT ще не протух — рівно 12 год)
        user_data = auth_manager.get_user_from_token(token)
        if user_data:
            if auth_manager.decode_token(token) is not None:
                return user_data
            auth_manager.remove_session(token)  # токен протух → знімаємо сесію

        payload = auth_manager.decode_token(token)
        if not payload:
            if required:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return None

        username = payload.get("sub")
        if not username:
            if required:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials",
                )
            return None

        result = await db.execute(
            select(UserDB).where(UserDB.username == username)
        )
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            if required:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found or inactive",
                )
            return None

        user_dict = {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role.value,
            "is_active": user.is_active
        }

        auth_manager.add_session(token, user_dict)
        return user_dict

    return _get_current_user

def require_role(required_role: UserRole):
    def role_checker(current_user: dict = Depends(get_current_user())):
        if current_user["role"] != required_role.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return current_user
    return role_checker


@router.post("/register", response_model=UserOut)
async def register_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user())
):
    if current_user["role"] != UserRole.admin.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can register new users"
        )
    
    result = await db.execute(
        select(UserDB).where(UserDB.username == user_data.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    hashed_password = auth_manager.get_password_hash(user_data.password)
    user = UserDB(
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        username=user_data.username,
        password_hash=hashed_password,
        role=user_data.role,
        is_active=True
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return UserOut(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        role=user.role,
        is_active=user.is_active
    )


@router.post("/login", response_model=Token)
async def login_form(
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    device_id: str = Form(None),
    db: AsyncSession = Depends(get_db)
):

    user = await auth_manager.authenticate_user(db, username, password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # --- Вибір ESP: менеджер ОБОВʼЯЗКОВО (онлайн + вільний, ексклюзив); адмін — поза правилом ---
    from app.main import esp_watchers, bind_esp, device_manager
    role = user.role.value
    device_id = (device_id or "").strip()
    if role != "admin":
        if not device_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Wybierz urządzenie ESP")
        dev = device_manager.get_device(device_id)
        if not dev or not dev.is_online:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Wybrane urządzenie jest niedostępne (offline)")
        watcher = esp_watchers.get(device_id)
        if watcher and watcher.get("user_id") != user.id:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Urządzenie zajęte przez {watcher.get('username')}")

    access_token = auth_manager.create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(hours=12)
    )

    user_dict = {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role.value,
        "is_active": user.is_active
    }
    auth_manager.add_session(access_token, user_dict)

    if role != "admin":
        bind_esp(device_id, user_dict, access_token)

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax"
    )
    
    return Token(access_token=access_token, token_type="bearer")


@router.post("/logout")
async def logout(
    response: Response,
    current_user: dict = Depends(get_current_user()),
    token: str = Depends(oauth2_scheme)
):
    from app.main import remove_user_from_all_esps, remove_user_ws_subscriptions
    user_id = current_user["id"]
    remove_user_from_all_esps(user_id)
    remove_user_ws_subscriptions(user_id)

    auth_manager.remove_session(token)
    response.delete_cookie("access_token")
    return {"message": "Successfully logged out"}

@router.get("/me")
async def me(
    request: Request,
    current_user: dict = Depends(get_current_user()),
    token: str = Depends(oauth2_scheme),
):
    from app.main import esp_watchers
    tok = token or get_token_from_cookie(request)
    bound = None
    for did, w in esp_watchers.items():
        if w.get("token") == tok:
            bound = did
            break
    return {**current_user, "bound_device": bound}


@router.get("/available-esps")
async def available_esps():
    """Публічно (до логіну): онлайн-ESP + хто на них слідкує."""
    from app.main import device_manager, esp_watchers
    result = []
    for did, dev in device_manager.get_online_devices().items():
        w = esp_watchers.get(did)
        result.append({
            "id": did,
            "name": dev.name,
            "watched_by": w.get("username") if w else None,
        })
    return result
