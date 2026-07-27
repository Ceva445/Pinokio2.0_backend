"""Менеджер прошивок ESP32 з кешуванням метаданих активної прошивки.

Ефективне зберігання: бінарник .bin лежить на диску (config.FIRMWARE_DIR),
у БД — лише метадані. У пам'яті кешуємо метадані активної прошивки (версія,
шлях, sha256), тож перевірка версії й видача 304 не чіпають ні БД, ні диск.
Сам файл читається/стрімиться лише коли реально треба віддати оновлення.

Кеш інвалідується при заливці/активації/видаленні.
"""
import logging
import hashlib
import uuid
from pathlib import Path
from typing import Optional, Dict, Any
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from models.db_firmware import FirmwareDB
from config import FIRMWARE_DIR

logger = logging.getLogger(__name__)


class FirmwareManager:
    def __init__(self):
        # None → кеш не прогрітий; {} → прогрітий, активної прошивки немає
        self._cache_meta: Optional[Dict[str, Any]] = None
        self._lock = asyncio.Lock()

    # ---------- ЧИТАННЯ (кеш) ----------

    async def get_active_meta(self, db: AsyncSession) -> Optional[Dict[str, Any]]:
        if self._cache_meta is not None:
            return self._cache_meta or None

        async with self._lock:
            if self._cache_meta is not None:
                return self._cache_meta or None

            stmt = select(FirmwareDB).where(FirmwareDB.is_active == True).limit(1)  # noqa: E712
            result = await db.execute(stmt)
            fw = result.scalar_one_or_none()

            self._cache_meta = self._meta_with_path(fw) if fw else {}
            return self._cache_meta or None

    async def get_active_version(self, db: AsyncSession) -> Optional[str]:
        meta = await self.get_active_meta(db)
        return meta["version"] if meta else None

    async def get_active_file(self, db: AsyncSession) -> Optional[Dict[str, Any]]:
        """
        Метадані активної прошивки разом з абсолютним шляхом до файлу.
        Бере з кешу; файл на диск не читає — його стрімить FileResponse.
        """
        meta = await self.get_active_meta(db)
        if not meta:
            return None
        path = FIRMWARE_DIR / meta["storage_name"]
        if not path.exists():
            logger.error("Firmware file missing on disk: %s", path)
            return None
        return {**meta, "path": path}

    # ---------- ЗАПИС ----------

    async def list_all(self, db: AsyncSession) -> list[Dict[str, Any]]:
        stmt = select(FirmwareDB).order_by(FirmwareDB.uploaded_at.desc())
        result = await db.execute(stmt)
        return [fw.to_dict() for fw in result.scalars().all()]

    async def save_new(
        self,
        db: AsyncSession,
        *,
        version: str,
        filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        uploaded_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Записати .bin на диск і зробити прошивку активною."""
        sha256 = hashlib.sha256(content).hexdigest()
        storage_name = f"{uuid.uuid4().hex}.bin"
        path = FIRMWARE_DIR / storage_name

        async with self._lock:
            # Пишемо файл на диск (поза event loop)
            await asyncio.to_thread(path.write_bytes, content)

            try:
                await db.execute(update(FirmwareDB).values(is_active=False))
                fw = FirmwareDB(
                    version=version,
                    filename=filename,
                    size=len(content),
                    content_type=content_type,
                    storage_name=storage_name,
                    sha256=sha256,
                    is_active=True,
                    uploaded_by=uploaded_by,
                )
                db.add(fw)
                await db.commit()
                await db.refresh(fw)
            except Exception:
                # Прибрати осиротілий файл, якщо БД впала
                await asyncio.to_thread(path.unlink, True)
                await db.rollback()
                raise

            self._cache_meta = self._meta_with_path(fw)
            logger.info("New firmware activated: v%s (%d bytes)", version, len(content))
            return self._cache_meta

    async def set_active(self, db: AsyncSession, firmware_id: int) -> Optional[Dict[str, Any]]:
        async with self._lock:
            fw = await db.get(FirmwareDB, firmware_id)
            if not fw:
                return None

            await db.execute(update(FirmwareDB).values(is_active=False))
            fw.is_active = True
            await db.commit()
            await db.refresh(fw)

            self._cache_meta = self._meta_with_path(fw)
            logger.info("Firmware switched to v%s (id=%d)", fw.version, fw.id)
            return self._cache_meta

    async def delete(self, db: AsyncSession, firmware_id: int) -> bool:
        async with self._lock:
            fw = await db.get(FirmwareDB, firmware_id)
            if not fw:
                return False
            was_active = fw.is_active
            storage_name = fw.storage_name
            await db.delete(fw)
            await db.commit()

            # Прибрати файл з диска
            await asyncio.to_thread((FIRMWARE_DIR / storage_name).unlink, True)

            if was_active:
                self.invalidate_cache()
            return True

    def invalidate_cache(self):
        self._cache_meta = None

    # ---------- helpers ----------

    @staticmethod
    def _meta_with_path(fw: FirmwareDB) -> Dict[str, Any]:
        return {**fw.to_dict(), "storage_name": fw.storage_name}


firmware_manager = FirmwareManager()
