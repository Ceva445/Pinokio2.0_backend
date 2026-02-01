from sqlalchemy import ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from db.base import Base
from datetime import datetime

class DeviceChangeTransaction(Base):
    __tablename__ = "device_change_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    device_id: Mapped[int | None] = mapped_column(
        ForeignKey("devices.id"), nullable=False
    )

    description: Mapped[str] = mapped_column(nullable=False)

    user = relationship("UserDB", back_populates="device_change_transactions")
    device = relationship("DeviceDB", back_populates="device_change_transactions")