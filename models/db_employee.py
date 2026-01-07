from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base

class EmployeeDB(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    last_name: Mapped[str]
    first_name: Mapped[str]
    rfid: Mapped[str] = mapped_column(unique=True, index=True)
    company: Mapped[str]

    devices = relationship(
        "DeviceDB",
        back_populates="employee",
        cascade="all, delete-orphan"
    )