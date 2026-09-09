from fastapi import Depends, HTTPException, status
from routers.auth import get_current_user
from models.db_user import UserRole

def require_admin(
    current_user: dict = Depends(get_current_user())
):
    if current_user["role"] != UserRole.admin.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins only"
        )
    return current_user

def require_admin_or_observer(
    current_user: dict = Depends(get_current_user())
):
    """Wejście do panelu administracyjnego bez prawa czegokolwiek tam zmieniać.

    Obserwator dostaje wyłącznie zakładkę z dashboardem — każdy inny ekran
    admina zostaje pod require_admin.
    """
    if current_user["role"] not in [UserRole.admin.value, UserRole.observer.value]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins or observers only"
        )
    return current_user

def require_dashboard_viewer(
    current_user: dict = Depends(get_current_user())
):
    """Kto może czytać liczby na dashboardzie: admin, kierownik i obserwator."""
    if current_user["role"] not in [
        UserRole.admin.value,
        UserRole.manager.value,
        UserRole.observer.value,
    ]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to view the dashboard"
        )
    return current_user

def forbid_observer(
    current_user: dict = Depends(get_current_user())
):
    """Ekrany i akcje związane z wydawaniem sprzętu — obserwatorowi wzbronione.

    Sam brak przycisku nie wystarcza: prawo do autoryzacji wydania bierze się
    z wpisu w esp_allowed_users, a ten zakłada zwykły endpoint subskrypcji.
    """
    if current_user["role"] == UserRole.observer.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Obserwator nie ma dostępu do wydawania sprzętu"
        )
    return current_user

def require_manager_or_admin(
    current_user: dict = Depends(get_current_user())
):
    if current_user["role"] not in [UserRole.manager.value, UserRole.admin.value]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Managers or Admins only"
        )
    return current_user
