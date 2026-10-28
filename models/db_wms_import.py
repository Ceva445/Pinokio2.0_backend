from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from db.base import Base


class WmsImportDB(Base):
    """Jedna paczka ruchów przysłana z WMS.

    Skrypt na serwerze WMS odpytuje Oracle i wysyła wynik tutaj, więc nikt nie
    musi pamiętać o eksporcie ani o wgrywaniu pliku. Trzymamy surowe ruchy, a
    nie gotowe zestawienie: kryterium "miał sprzęt w rękach" liczy się przy
    otwieraniu raportu, z aktualnego stanu wydań.
    """

    __tablename__ = "wms_imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # "push" — przysłane przez skrypt, "upload" — wgrane ręcznie na ekranie.
    source: Mapped[str] = mapped_column(String(16), default="push")
    # Skąd przyszło: nazwa maszyny ze skryptu. Przy dwóch źródłach naraz to
    # jedyne, co pozwala powiedzieć, które z nich zamilkło.
    origin: Mapped[str | None] = mapped_column(String(100), nullable=True)

    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    period_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    period_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Surowe wiersze z WMS, dokładnie takie, jakie przyszły.
    payload: Mapped[list] = mapped_column(JSON, default=list)
