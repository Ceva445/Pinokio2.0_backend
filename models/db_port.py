from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base


class DevicePortDB(Base):
    __tablename__ = "device_ports"

    id: Mapped[int] = mapped_column(primary_key=True)
    port_number: Mapped[str] = mapped_column(String, nullable=False)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id"), nullable=False
    )

    device = relationship("DeviceDB", back_populates="ports")
