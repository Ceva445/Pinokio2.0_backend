"""Головний файл додатку"""
import logging
import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from config import STATIC_DIR, LOG_CONFIG
from managers.connection_manager import ConnectionManager
from managers.device_manager import DeviceManager
from routers import api, pages, websocket
from fastapi.middleware.cors import CORSMiddleware

# Налаштування логування
logging.basicConfig(**LOG_CONFIG)
logger = logging.getLogger(__name__)

# Глобальні менеджери
device_manager = DeviceManager(timeout_minutes=10)
manager = ConnectionManager(device_manager)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Контекст життя додатку"""
    logger.info("ESP32 Multi-Device Monitor started")
    
    cleanup_task = asyncio.create_task(cleanup_offline_devices())
    
    yield
    
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("ESP32 Multi-Device Monitor stopped")


async def cleanup_offline_devices():
    """Фонова задача для очищення офлайн пристроїв"""
    while True:
        try:
            await asyncio.sleep(300)  # кожні 5 хвилин
            offline_devices = device_manager.cleanup_offline_devices()
            if offline_devices:
                # Сповістити клієнтів про зміни статусу
                await manager.broadcast_to_all(
                    message_type="device_status_update",
                    data=device_manager.get_all_devices_status()
                )
        except Exception as exc:
            logger.error("Error in cleanup task: %s", exc)


# Ініціалізація додатку
app = FastAPI(
    title="ESP32 Multi-Device Monitor",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Монтування статичних файлів
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Підключення маршрутів
app.include_router(api.router)
app.include_router(websocket.router)
app.include_router(pages.router)
