from sqlalchemy import ForeignKey, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from db.base import Base
import enum
from datetime import datetime


class TransactionType(enum.Enum):
    registered = "registered"
    unregistered = "unregistered"


# Wartość kolumny `source` dla zwrotu zdjętego ręcznie z panelu administratora.
TRANSACTION_SOURCE_PANEL = "panel"


class TransactionDB(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type"),
        nullable=False
    )

    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    device_id: Mapped[int | None] = mapped_column(
        ForeignKey("devices.id"), nullable=False
    )
    # Менеджер (або адмін), який своїм підключенням до ESP дозволив видачу.
    # NULL для старих записів і для реєстрацій без авторизованого слухача.
    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    # Skąd wziął się wiersz. NULL = karta przyłożona do czytnika; tak powstały
    # wszystkie dotychczasowe zapisy i tak nadal powstaje ich większość.
    # "panel" = zwrot zdjęty ręcznie przez administratora z ekranu urządzeń.
    # Takiego zwrotu nikt nie potwierdza kartą, więc w historii w miejscu
    # pracownika pokazujemy tego, kto go wykonał — inaczej wiersz nie różniłby
    # się od zdjęcia sprzętu na czytniku.
    source: Mapped[str | None] = mapped_column(String(16), nullable=True)

    employee = relationship("EmployeeDB", back_populates="transactions")
    device = relationship("DeviceDB", back_populates="transactions")
    manager = relationship("UserDB")