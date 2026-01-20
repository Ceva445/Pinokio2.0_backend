"""Маршрути для HTML сторінок"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from config import templates

router = APIRouter(tags=["Pages"])


@router.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    """Головна сторінка"""
    return templates.TemplateResponse(
        "home.html",
        {"request": request}
    )


@router.get("/monitor", response_class=HTMLResponse)
async def monitor(request: Request) -> HTMLResponse:
    """Сторінка моніторингу"""
    return templates.TemplateResponse(
        "monitor.html",
        {"request": request}
    )