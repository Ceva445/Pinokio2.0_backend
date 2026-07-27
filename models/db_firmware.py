"""Модель прошивки ESP32 (для OTA-оновлень)"""
from sqlalchemy import String, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from db.base import Base
from datetime import datetime, timezone


class FirmwareDB(Base):
    """
    Метадані прошивок ESP32. Сам бінарник .bin лежить на диску
    (config.FIRMWARE_DIR), а тут — тільки посилання на нього + версія/хеш.

    Так БД лишається легкою, віддача файлу стрімиться з диска (без завантаження
    в пам'ять), а sha256 дозволяє перевіряти цілісність і дедуплікувати.
    Активна прошивка — та, у якої is_active == True (одночасно тільки одна).
    """
    __tablename__ = "firmware"

    id: Mapped[int] = mapped_column(primary_key=True)

    version: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")

    # Ім'я файлу в FIRMWARE_DIR (не абсолютний шлях — щоб не залежати від хоста)
    storage_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    uploaded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )

    def to_dict(self):
        return {
            "id": self.id,
            "version": self.version,
            "filename": self.filename,
            "size": self.size,
            "content_type": self.content_type,
            "sha256": self.sha256,
            "is_active": self.is_active,
            "uploaded_by": self.uploaded_by,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
        }
