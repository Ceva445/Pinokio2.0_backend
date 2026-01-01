from sqlalchemy import String, Enum
from sqlalchemy.orm import Mapped, mapped_column
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
