"""Модель системної конфігурації"""
from sqlalchemy import String, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from db.base import Base
from datetime import datetime


class SystemConfigDB(Base):
    __tablename__ = "system_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Таймаути та інтервали (в секундах)
    access_token_expire_minutes: Mapped[int] = mapped_column(Integer, default=30)
    device_timeout_minutes: Mapped[int] = mapped_column(Integer, default=5)
    registration_timeout_seconds: Mapped[int] = mapped_column(Integer, default=7)
    device_cleanup_interval_seconds: Mapped[int] = mapped_column(Integer, default=300)  # 5 хвилин
    auth_cleanup_interval_seconds: Mapped[int] = mapped_column(Integer, default=3600)  # 1 година
    
    # Довгі таймаути
    device_not_returned_hours: Mapped[int] = mapped_column(Integer, default=12)
    
    # Настройки реєстрації
    allow_registration_without_login: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Метаінформація
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        """Конвертувати в словник"""
        return {
            "id": self.id,
            "access_token_expire_minutes": self.access_token_expire_minutes,
            "device_timeout_minutes": self.device_timeout_minutes,
            "registration_timeout_seconds": self.registration_timeout_seconds,
            "device_cleanup_interval_seconds": self.device_cleanup_interval_seconds,
            "auth_cleanup_interval_seconds": self.auth_cleanup_interval_seconds,
            "device_not_returned_hours": self.device_not_returned_hours,
            "allow_registration_without_login": self.allow_registration_without_login,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
