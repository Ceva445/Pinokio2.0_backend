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

