"""API для управління системною конфігурацією (тільки для адміністраторів)"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging

from db.session import get_db
from app.dependencies.admin import require_admin
from managers.config_manager import config_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api/system-config", tags=["Admin System Config"])


class ConfigUpdateRequest(BaseModel):
    """Запит для оновлення конфігурації"""
    access_token_expire_minutes: Optional[int] = None
    device_timeout_minutes: Optional[int] = None
    registration_timeout_seconds: Optional[int] = None
    device_cleanup_interval_seconds: Optional[int] = None
    auth_cleanup_interval_seconds: Optional[int] = None
    device_not_returned_hours: Optional[int] = None
    allow_registration_without_login: Optional[bool] = None
    temporary_card_duration_hours: Optional[int] = None
    email_notifications_enabled: Optional[bool] = None
    email_send_times: Optional[str] = None
    email_send_times_saturday: Optional[str] = None
    email_send_times_sunday: Optional[str] = None
    manager_idle_logout_minutes: Optional[int] = None

    class Config:
        json_schema_extra = {
            "example": {
                "access_token_expire_minutes": 30,
                "device_timeout_minutes": 5,
                "registration_timeout_seconds": 7,
                "allow_registration_without_login": False,
                "temporary_card_duration_hours": 72
            }
        }


@router.get("")
async def get_config(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Отримати поточну конфігурацію системи.
    Доступно тільки для адміністраторів.
    """
    try:
        config = await config_manager.get_config(db)
        return {
            "status": "ok",
            "config": config
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error loading config: {str(e)}"
        )


@router.put("")
async def update_config(
    request: ConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Оновити конфігурацію системи.
    Доступно тільки для адміністраторів.
    
    Передавайте тільки поля, які хочете оновити.
    """
    try:
        # Фільтруємо None значення - відправляємо тільки встановлені поля
        updates = {k: v for k, v in request.model_dump().items() if v is not None}
        
        # Валідація значень
        if "access_token_expire_minutes" in updates and updates["access_token_expire_minutes"] <= 0:
            raise ValueError("access_token_expire_minutes must be > 0")
        if "device_timeout_minutes" in updates and updates["device_timeout_minutes"] <= 0:
            raise ValueError("device_timeout_minutes must be > 0")
        if "registration_timeout_seconds" in updates and updates["registration_timeout_seconds"] <= 0:
            raise ValueError("registration_timeout_seconds must be > 0")
        if "device_cleanup_interval_seconds" in updates and updates["device_cleanup_interval_seconds"] <= 0:
            raise ValueError("device_cleanup_interval_seconds must be > 0")
        if "auth_cleanup_interval_seconds" in updates and updates["auth_cleanup_interval_seconds"] <= 0:
            raise ValueError("auth_cleanup_interval_seconds must be > 0")
        if "device_not_returned_hours" in updates and updates["device_not_returned_hours"] <= 0:
            raise ValueError("device_not_returned_hours must be > 0")
        if "temporary_card_duration_hours" in updates and updates["temporary_card_duration_hours"] <= 0:
            raise ValueError("temporary_card_duration_hours must be > 0")

        # Валідація розкладів email (будні/субота/неділя): "HH:MM,HH:MM..."
        # Порожній рядок дозволено = того дня не слати. Нормалізуємо (унікальні, сортовані).
        for _field in ("email_send_times", "email_send_times_saturday", "email_send_times_sunday"):
            if _field in updates:
                times = []
                for part in str(updates[_field] or "").split(","):
                    part = part.strip()
                    if not part:
                        continue
                    try:
                        hh, mm = part.split(":")
                        h, m = int(hh), int(mm)
                        if not (0 <= h <= 23 and 0 <= m <= 59):
                            raise ValueError()
                        times.append(f"{h:02d}:{m:02d}")
                    except Exception:
                        raise ValueError(f"Nieprawidłowy czas: '{part}' (oczekiwano HH:MM)")
                updates[_field] = ",".join(sorted(set(times)))

        updated_config = await config_manager.update_config(db, updates)
        
        # Оновити менеджери з новими значеннями
        _update_managers(updated_config)
        
        logger.info(f"System configuration updated: {updates}")
        
        return {
            "status": "ok",
            "message": "Configuration updated successfully",
            "config": updated_config
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating config: {str(e)}"
        )


def _update_managers(config: Dict[str, Any]):
    """
    Оновити менеджери з новими значеннями таймаутів.
    Це забезпечує миттєве застосування змін для request-обробки.
    
    Фонові задачи (cleanup functions) беруть конфіги безпосередньо з config_manager.
    """
    try:
        # Імпортуємо тут, щоб уникнути циклічних імпортів
        from app.main import device_manager, registration_manager
        
        if "device_timeout_minutes" in config:
            device_manager.update_timeout(config["device_timeout_minutes"])
        
        if "registration_timeout_seconds" in config:
            registration_manager.update_timeout(config["registration_timeout_seconds"])
        
        logger.info("Device and registration managers updated with new timeouts")
    except Exception as e:
        logger.error(f"Error updating managers: {e}")
        # Не піднімаємо помилку, оскільки конфіг все одно зберігся в БД


@router.post("/refresh-cache")
async def refresh_cache(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Обновити кеш конфігурації.
    Доступно тільки для адміністраторів.
    """
    try:
        config_manager.invalidate_cache()
        config = await config_manager.get_config(db)
        
        # Також оновити менеджери
        _update_managers(config)
        
        return {
            "status": "ok",
            "message": "Cache refreshed",
            "config": config
        }
    except Exception as e:
        logger.error(f"Error refreshing cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error refreshing cache: {str(e)}"
        )
