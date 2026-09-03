from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base

class EmployeeDB(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    last_name: Mapped[str]
    first_name: Mapped[str]
    rfid: Mapped[str] = mapped_column(unique=True, index=True)
    company: Mapped[str]
    wms_login: Mapped[str] = mapped_column(unique=True, index=True, nullable=True)
    department: Mapped[str] = mapped_column(nullable=True, index=True)
    expired: Mapped[bool] = mapped_column(default=False)
    # Майданчик, до якого приписаний працівник (довідник sites)
    site_id: Mapped[int | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )

    devices = relationship(
        "DeviceDB",
        back_populates="employee",
        cascade="all, delete-orphan"
    )
    transactions = relationship(
        "TransactionDB",
        back_populates="employee"
    )
    site = relationship("SiteDB", back_populates="employees")