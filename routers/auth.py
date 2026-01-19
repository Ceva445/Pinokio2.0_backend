"""Маршрути для автентифікації користувачів"""
from fastapi import APIRouter, Depends, HTTPException, status, Form
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


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_data = auth_manager.get_user_from_token(token)
    if user_data:
        return user_data
    
    payload = auth_manager.decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    
    result = await db.execute(
        select(UserDB).where(UserDB.username == username)
    )
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    
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


def require_role(required_role: UserRole):
    def role_checker(current_user: dict = Depends(get_current_user)):
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
    current_user: dict = Depends(get_current_user)
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
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):

    user = await auth_manager.authenticate_user(db, username, password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = auth_manager.create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=30)
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
    
    return Token(access_token=access_token, token_type="bearer")


@router.post("/logout")
async def logout(
    current_user: dict = Depends(get_current_user),
    token: str = Depends(oauth2_scheme)
):
    """Вихід з системи"""
    auth_manager.remove_session(token)
    return {"message": "Successfully logged out"}
