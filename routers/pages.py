"""Маршрути для HTML сторінок"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from config import templates
from routers.auth import get_current_user

router = APIRouter(tags=["Pages"])


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
    print("Current user in monitor:", current_user["role"] if current_user else "None")
    return templates.TemplateResponse(
        "monitor.html",
        {
            "request": request,
            "current_user": current_user
        }
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )