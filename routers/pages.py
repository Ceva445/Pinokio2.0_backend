"""Маршрути для HTML сторінок"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from config import templates
from models.db_user import UserRole
from routers.auth import get_current_user

router = APIRouter(tags=["Pages"])


def _block_observer(current_user: dict | None) -> None:
    """Monitor to ekran wydawania sprzętu — obserwatorowi nic tam nie wolno.

    Gość (bez logowania) monitor widzi, ale w trybie informacyjnym; obserwator
    jest zalogowany, więc bez tego sprawdzenia miałby ten ekran normalnie.
    """
    if current_user and current_user.get("role") == UserRole.observer.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Obserwator nie ma dostępu do monitora"
        )


@router.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    """Головна сторінка"""
    return templates.TemplateResponse(
        "home.html",
        {"request": request}
    )


@router.get("/monitor", response_class=HTMLResponse)
async def monitor(
    request: Request,
    current_user: dict = Depends(get_current_user(False))
) -> HTMLResponse:
    _block_observer(current_user)
    return templates.TemplateResponse(
        "monitor.html",
        {
            "request": request,
            "current_user": current_user
        }
    )


@router.get("/monitor2", response_class=HTMLResponse)
async def monitor2(
    request: Request,
    current_user: dict = Depends(get_current_user(False))
) -> HTMLResponse:
    _block_observer(current_user)
    return templates.TemplateResponse(
        "monitor2.html",
        {
            "request": request,
            "current_user": current_user
        }
    )


@router.get("/change-password", response_class=HTMLResponse)
async def change_password_page(request: Request):
    return templates.TemplateResponse(
        "change_password.html",
        {"request": request}
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )