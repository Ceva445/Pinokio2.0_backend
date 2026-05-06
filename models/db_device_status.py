from sqlalchemy import String, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base
import enum


class DeviceStatusType(enum.Enum):
    work = "work"
    service = "service"
    wanted = "wanted"
    old_wanted = "old_wanted"
    kantor = "kantor"


class DeviceStatusDB(Base):
    __tablename__ = "device_statuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id"), nullable=False
    )
    status: Mapped[DeviceStatusType] = mapped_column(
        Enum(DeviceStatusType, name="device_status_type"),
        nullable=False,
        default=DeviceStatusType.work
    )
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    # Relationship to device
    device = relationship("DeviceDB", back_populates="statuses")
