from datetime import datetime

from sqlalchemy import DateTime, String, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base
import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    manager = "manager"
    # Obserwator: wchodzi do panelu tylko po to, żeby patrzeć na dashboard.
    # Nie wydaje sprzętu i nie ma wstępu na monitor.
    observer = "observer"


class UserDB(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(50))
    last_name: Mapped[str] = mapped_column(String(50))
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", create_constraint=True),
        default=UserRole.manager
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    # Wymuś zmianę hasła przy pierwszym logowaniu: użytkownik loguje się
    # hasłem od admina, po czym musi ustawić własne.
    must_change_password: Mapped[bool] = mapped_column(default=False)

    # Granica ważności sesji. Token wystawiony przed tą chwilą jest martwy,
    # nawet jeśli backend zdążył się w międzyczasie zrestartować i nie pamięta
    # już żadnych sesji. Ustawia ją administrator, wyrzucając użytkownika.
    sessions_valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    device_change_transactions = relationship(
        "models.device_transaction.DeviceChangeTransaction",
        back_populates="user"
    )