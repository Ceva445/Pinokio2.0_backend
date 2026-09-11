from datetime import datetime

from sqlalchemy import ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from db.base import Base


class DamageReportDB(Base):
    """Protokół uszkodzenia sprzętu.

    Zgłasza kierownik albo administrator: wybiera urządzenie i opisuje, co się
    stało. Zapis zostaje w bazie, a treść idzie mailem do grupy ALL.
    """

    __tablename__ = "damage_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id"), nullable=False, index=True
    )

    # Kto spisał protokół.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    # Kto miał sprzęt w chwili zgłoszenia. Zapisujemy osobno, bo urządzenie
    # pojedzie dalej — do serwisu albo do kogoś innego — a protokół ma zostać
    # z odpowiedzią na pytanie "u kogo to się stało".
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )

    description: Mapped[str] = mapped_column(Text, nullable=False)

    device = relationship("DeviceDB")
    user = relationship("UserDB")
    employee = relationship("EmployeeDB")
