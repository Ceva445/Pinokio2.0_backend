from sqlalchemy import String, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base
import enum

class DeviceType(enum.Enum):
    scanner = "scanner"
    printer = "printer"

class DeviceDB(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    rfid: Mapped[str] = mapped_column(String, unique=True, index=True)
    serial_number: Mapped[str] = mapped_column(String, unique=True)
    type: Mapped[DeviceType]
    enabled: Mapped[bool] = mapped_column(default=True)
    ip: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)

    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )

    employee = relationship("EmployeeDB", back_populates="devices")
    ports = relationship(
        "DevicePortDB",
        back_populates="device",
        cascade="all, delete-orphan"
    )
    transactions = relationship(
            "TransactionDB",
            back_populates="device"
        )
    
    device_change_transactions = relationship(
        "models.device_transaction.DeviceChangeTransaction",
        back_populates="device",
        cascade="all, delete-orphan"
    )
    status_id: Mapped[int | None] = mapped_column(
        ForeignKey("device_statuses.id"),
        nullable=True
    )

    status = relationship("DeviceStatusDB")