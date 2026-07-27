"""API для керування прошивками ESP32 (тільки для адміністраторів)."""
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from app.dependencies.admin import require_admin
from managers.firmware_manager import firmware_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api/firmware", tags=["Admin Firmware"])

MAX_FIRMWARE_SIZE = 4 * 1024 * 1024  # 4 МБ — з запасом на ESP32


@router.get("")
async def list_firmware(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """Активна прошивка + повна історія залитих прошивок."""
    active = await firmware_manager.get_active_meta(db)
    history = await firmware_manager.list_all(db)
    return {"status": "ok", "active": active, "history": history}


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_firmware(
    version: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """
    Залити нову прошивку і одразу зробити її активною.
    Після цього кеш оновлюється, і ESP при наступному запиті отримає
    новий X-Firmware-Version.
    """
    version = (version or "").strip()
    if not version:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "version is required")

    filename = file.filename or "firmware.bin"
    if not filename.lower().endswith(".bin"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Oczekiwany plik .bin")

    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pusty plik")
    if len(content) > MAX_FIRMWARE_SIZE:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Plik za duży (max {MAX_FIRMWARE_SIZE // (1024 * 1024)} MB)",
        )

    meta = await firmware_manager.save_new(
        db,
        version=version,
        filename=filename,
        content=content,
        content_type=file.content_type or "application/octet-stream",
        uploaded_by=current_user.get("username"),
    )
    return {"status": "ok", "message": "Firmware uploaded", "active": meta}


@router.post("/{firmware_id}/activate")
async def activate_firmware(
    firmware_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """Активувати вже залиту прошивку (rollback на попередню версію)."""
    meta = await firmware_manager.set_active(db, firmware_id)
    if not meta:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Firmware not found")
    return {"status": "ok", "message": "Firmware activated", "active": meta}


@router.delete("/{firmware_id}")
async def delete_firmware(
    firmware_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    ok = await firmware_manager.delete(db, firmware_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Firmware not found")
    return {"status": "ok", "message": "Firmware deleted"}
