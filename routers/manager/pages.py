from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from config import templates
from app.dependencies.admin import require_manager_or_admin

router = APIRouter(
    prefix="/manager",
    tags=["Manager pages"],
)

@router.get("/", response_class=HTMLResponse)
async def manager_dashboard(
    request: Request,
    current_user: dict = Depends(require_manager_or_admin)
):
    return templates.TemplateResponse(
        "manager/dashboard.html",
        {
            "request": request,
            "user": current_user
        }
    )


@router.get("/registration", response_class=HTMLResponse)
async def manager_registration(
    request: Request,
    current_user: dict = Depends(require_manager_or_admin)
):
    return templates.TemplateResponse(
        "manager/registration.html",
        {
            "request": request,
            "user": current_user
        }
    )


@router.get("/transactions", response_class=HTMLResponse)
async def manager_transactions(
    request: Request,
    current_user: dict = Depends(require_manager_or_admin)
):
    return templates.TemplateResponse(
        "manager/transactions.html",
        {
            "request": request,
            "user": current_user
        }
    )


# ===============================
# DEVICES PAGE (tylko podgląd)
# ===============================

@router.get("/devices", response_class=HTMLResponse)
async def manager_devices(
    request: Request,
    current_user: dict = Depends(require_manager_or_admin)
):
    return templates.TemplateResponse(
        "manager/devices/list.html",
        {"request": request, "user": current_user}
    )


# ===============================
# PROTOKÓŁ USZKODZENIA
# ===============================

@router.get("/damage-reports", response_class=HTMLResponse)
async def manager_damage_reports(
    request: Request,
    current_user: dict = Depends(require_manager_or_admin)
):
    return templates.TemplateResponse(
        "manager/damage_reports.html",
        {"request": request, "user": current_user}
    )


# ===============================
# TEMPORARY EMPLOYEES PAGES
# ===============================

@router.get("/temporary-employees/create", response_class=HTMLResponse)
async def temporary_employee_create_page(
    request: Request,
    current_user: dict = Depends(require_manager_or_admin)
):
    return templates.TemplateResponse(
        "manager/temporary_employees/create.html",
        {"request": request}
    )
