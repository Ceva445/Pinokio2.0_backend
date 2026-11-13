"""Karta gościa pożyczona pracownikowi, który zapomniał własnej.

Pożyczka jest osobnym wierszem, a nie podmianą numeru w kadrach: kolumna
employees.rfid zostaje nietknięta, więc własna karta działa dalej, a cała
historia i statystyka pracownika zostają przy jednym rekordzie. Czytnik, nie
znajdując karty wśród pracowników, pyta jeszcze o aktywną pożyczkę.

Czas trzymamy jako naiwne UTC — tak samo jak guests.last_used_at, z którym
zadanie w tle porównuje te daty.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from db.base import Base

# Dlaczego pożyczka się skończyła — widać w historii i w logu.
POWOD_TERMIN = "timeout"        # minął termin ważności
POWOD_WLASNA_KARTA = "own_card"  # pracownik przyłożył swoją kartę
POWOD_RECZNY = "manual"          # administrator zwolnił kartę z panelu


class BorrowedCardDB(Base):
    __tablename__ = "borrowed_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )
    guest_id: Mapped[int] = mapped_column(
        ForeignKey("guests.id"), nullable=False, index=True
    )
    # Kopia numeru karty. Czytnik szuka po nim pracownika, a po zwrocie ta sama
    # karta trafia do kogoś innego — wiersz dalej mówi, czym kto wtedy skanował.
    rfid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    issued_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Puste = pożyczka trwa. Po zwrocie data i powód zostają w historii.
    returned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    returned_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)

    issued_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    employee = relationship("EmployeeDB")
    guest = relationship("DBGuest")
    issued_by = relationship("UserDB")

    @property
    def aktywna(self) -> bool:
        return self.returned_at is None
