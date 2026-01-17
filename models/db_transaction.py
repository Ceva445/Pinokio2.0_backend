from sqlalchemy import ForeignKey, DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from db.base import Base
import enum
from datetime import datetime


class TransactionType(enum.Enum):
    registered = "registered"
    unregistered = "unregistered"


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

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    device_id: Mapped[int | None] = mapped_column(
        ForeignKey("devices.id"), nullable=False
    )

    user = relationship("EmployeeDB", back_populates="transactions")
    device = relationship("DeviceDB", back_populates="transactions")