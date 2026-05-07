from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base


class DeviceStatusDB(Base):
    __tablename__ = "device_statuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False
    )
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    # Relationship to device
    device = relationship("DeviceDB", back_populates="statuses")
