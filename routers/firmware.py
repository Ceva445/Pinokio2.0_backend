"""Публічні ендпоінти прошивки для ESP32 (OTA)."""
import logging

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from managers.firmware_manager import firmware_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/firmware", tags=["Firmware (ESP32)"])


@router.get("/version")
async def firmware_version(db: AsyncSession = Depends(get_db)):
    """Поточна активна версія прошивки (для дебагу/моніторингу)."""
    version = await firmware_manager.get_active_version(db)
    return {"version": version}


@router.get("/download")
async def firmware_download(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Віддає активну прошивку для OTA.

    ESP (HTTPUpdate) шле свою поточну версію в хедері `x-ESP32-version`.
    - версія збігається з активною → 304 Not Modified (нічого не качаємо);
    - інакше → 200 з тілом .bin.

    Порівняння версії робиться по кешу (без читання бінарника з БД),
    бінарник тягнеться лише коли реально треба віддати оновлення.
    """
    current = request.headers.get("x-ESP32-version", "")

    meta = await firmware_manager.get_active_meta(db)
    if not meta:
        # Активної прошивки немає → оновлювати нема на що.
        # Віддаємо 304, а не 404, щоб ESP трактував це як "оновлень нема"
        # і не логував OTA FAILED при кожній перевірці.
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    # Порівняння версії — по кешу, без диску/БД
    if current and current == meta["version"]:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    fw = await firmware_manager.get_active_file(db)
    if not fw:
        # Кеш казав що є, але файлу вже нема — рідкісний гонковий випадок
        firmware_manager.invalidate_cache()
        return Response(status_code=status.HTTP_404_NOT_FOUND)

    # FileResponse стрімить файл з диска (sendfile), не тягне в пам'ять
    return FileResponse(
        path=fw["path"],
        media_type="application/octet-stream",
        filename=fw["filename"],
        headers={
            "X-Firmware-Version": fw["version"],
            "X-Firmware-SHA256": fw["sha256"],
        },
    )
