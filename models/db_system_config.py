"""Модель системної конфігурації"""
from sqlalchemy import String, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from db.base import Base
from datetime import datetime, timezone


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
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    # Настройка довжини часу дозволу працювати працівнику на тимчасовій карті в шодинах
    temporary_card_duration_hours: Mapped[int] = mapped_column(Integer, default=72)

    # Розклад email-нотифікацій про неповернені пристрої
    email_notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Час(и) відправки за день, HH:MM через кому (час Europe/Warsaw). Напр. "09:00,15:00"
    # email_send_times — будні (пн-пт); окремі розклади для суботи й неділі.
    email_send_times: Mapped[str] = mapped_column(String, default="09:00,15:00")
    email_send_times_saturday: Mapped[str] = mapped_column(String, default="09:00,15:00")
    email_send_times_sunday: Mapped[str] = mapped_column(String, default="09:00,15:00")

    # Авто-вилогування менеджера при бездіяльності на його ESP (у хвилинах).
    # 0 = вимкнено. Бездіяльність = на пристрої ніхто нічого не сканує.
    manager_idle_logout_minutes: Mapped[int] = mapped_column(Integer, default=15)

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
            "temporary_card_duration_hours": self.temporary_card_duration_hours,
            "email_notifications_enabled": self.email_notifications_enabled,
            "email_send_times": self.email_send_times,
            "email_send_times_saturday": self.email_send_times_saturday,
            "email_send_times_sunday": self.email_send_times_sunday,
            "manager_idle_logout_minutes": self.manager_idle_logout_minutes,
        }
