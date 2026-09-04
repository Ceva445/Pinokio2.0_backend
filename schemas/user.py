from pydantic import BaseModel, EmailStr
from enum import Enum
from typing import Optional


class UserRole(str, Enum):
    admin = "admin"
    manager = "manager"


class UserBase(BaseModel):
    first_name: str
    last_name: str
    username: str
    role: UserRole = UserRole.manager


class UserCreate(UserBase):
    password: str
    must_change_password: bool = False


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    password: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    must_change_password: Optional[bool] = None


class UserLogin(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    """Zmiana hasła przez samego użytkownika (pierwsze logowanie)."""
    new_password: str


class UserOut(UserBase):
    id: int
    is_active: bool
    must_change_password: bool = False

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None