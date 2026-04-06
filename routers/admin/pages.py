from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from config import templates
from app.dependencies.admin import require_admin

router = APIRouter(
    prefix="/admin",
    tags=["Admin pages"],
)

@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    current_user: dict = Depends(require_admin)
):
    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.get("/employees", response_class=HTMLResponse)
async def employees_list(
    request: Request,
    current_user: dict = Depends(require_admin)
):
    return templates.TemplateResponse(
        "admin/employees/list.html",
        {"request": request}
    )


@router.get("/employees/create", response_class=HTMLResponse)
async def employee_create_page(
    request: Request,
    current_user: dict = Depends(require_admin)
):
    return templates.TemplateResponse(
        "admin/employees/create.html",
        {"request": request}
    )

@router.get("/employees/{employee_id}", response_class=HTMLResponse)
async def employee_detail(
    employee_id: int,
    request: Request,
    current_user: dict = Depends(require_admin)
):
    return templates.TemplateResponse(
        "admin/employees/detail.html",
        {
            "request": request,
            "employee_id": employee_id
        }
    )


# ===============================
# DEVICES PAGES
# ===============================

@router.get("/devices", response_class=HTMLResponse)
async def devices_list(
    request: Request,
    current_user: dict = Depends(require_admin)
):
    return templates.TemplateResponse(
        "admin/devices/list.html",
        {"request": request}
    )


@router.get("/devices/create", response_class=HTMLResponse)
async def device_create_page(
    request: Request,
    current_user: dict = Depends(require_admin)
):
    return templates.TemplateResponse(
        "admin/devices/create.html",
        {"request": request}
    )


@router.get("/devices/{device_id}", response_class=HTMLResponse)
async def device_detail(
    device_id: int,
    request: Request,
    current_user: dict = Depends(require_admin)
):
    return templates.TemplateResponse(
        "admin/devices/detail.html",
        {
            "request": request,
            "device_id": device_id
        }
    )


@router.get("/users", response_class=HTMLResponse)
async def users_list(
    request: Request,
    current_user=Depends(require_admin)
):
    return templates.TemplateResponse(
        "admin/users/list.html",
        {"request": request}
    )

@router.get("/users/create", response_class=HTMLResponse)
async def user_create_page(
    request: Request,
    current_user=Depends(require_admin)
):
    return templates.TemplateResponse(
        "admin/users/create.html",
        {"request": request}
    )

@router.get("/users/{user_id}", response_class=HTMLResponse)
async def user_detail(
    user_id: int,
    request: Request,
    current_user=Depends(require_admin)
):
    return templates.TemplateResponse(
        "admin/users/detail.html",
        {
            "request": request,
            "user_id": user_id
        }
    )

# ===============================
# TRANSACTIONS PAGES
# ===============================

@router.get("/transactions", response_class=HTMLResponse)
async def transactions_list(
    request: Request,
    current_user: dict = Depends(require_admin)
):
    return templates.TemplateResponse(
        "admin/transactions/list.html",
        {"request": request}
    )

# ===============================
# DEVICE TRANSACTIONS PAGES
# ===============================

@router.get("/device-transactions", response_class=HTMLResponse)
async def device_transactions_list(
    request: Request,
    current_user: dict = Depends(require_admin)
):
    return templates.TemplateResponse(
        "admin/device_transactions/list.html",
        {"request": request}
    )

# DEPARTMENT MANAGERS
@router.get("/department-managers", response_class=HTMLResponse)
async def department_managers_list(request: Request, current_user=Depends(require_admin)):
    return templates.TemplateResponse(
        "admin/department_managers/list.html",
        {"request": request}
    )

@router.get("/department-managers/create", response_class=HTMLResponse)
async def department_manager_create(request: Request, current_user=Depends(require_admin)):
    return templates.TemplateResponse(
        "admin/department_managers/create.html",
        {"request": request}
    )

@router.get("/department-managers/{manager_id}", response_class=HTMLResponse)
async def department_manager_detail(manager_id: int, request: Request, current_user=Depends(require_admin)):
    return templates.TemplateResponse(
        "admin/department_managers/detail.html",
        {"request": request, "manager_id": manager_id}
    )

# ===============================
# SYSTEM CONFIG PAGE
# ===============================

@router.get("/system-config", response_class=HTMLResponse)
async def system_config_page(
    request: Request,
    current_user: dict = Depends(require_admin)
):
    return templates.TemplateResponse(
        "admin/system_config.html",
        {"request": request}
    )