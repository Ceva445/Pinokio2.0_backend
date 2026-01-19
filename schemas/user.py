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


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    password: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(UserBase):
    id: int
    is_active: bool

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None