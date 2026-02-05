"""Головний файл додатку"""
import logging
import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from config import STATIC_DIR, LOG_CONFIG
from managers.connection_manager import ConnectionManager
from managers.device_manager import DeviceManager
from routers import api, pages, websocket, auth
from fastapi.middleware.cors import CORSMiddleware
from managers.registration_manager import RegistrationManager
from managers.auth_manager import auth_manager
from pathlib import Path
import sys
from routers.admin.api import router as admin_api_router
from routers.admin.api_users import router as admin_users_api_router
from routers.admin.pages import router as admin_pages_router
from routers.admin.admin_transactions import router as admin_transactions_router
from routers.admin.admin_device_transactions import router as admin_device_transactions_router

# Налаштування логування
logging.basicConfig(**LOG_CONFIG)
logger = logging.getLogger(__name__)

# Глобальні менеджери
device_manager = DeviceManager(timeout_minutes=10)
manager = ConnectionManager(device_manager)
registration_manager = RegistrationManager(timeout_seconds=60)

esp_allowed_users: dict[str, set[int]] = {}

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Контекст життя додатку"""
    logger.info("ESP32 Multi-Device Monitor started")
    
    cleanup_task = asyncio.create_task(cleanup_offline_devices())
    auth_cleanup_task = asyncio.create_task(cleanup_auth_sessions())
    
    yield
    
    cleanup_task.cancel()
    auth_cleanup_task.cancel()
    try:
        await cleanup_task
        await auth_cleanup_task
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


async def cleanup_auth_sessions():
    while True:
        try:
            await asyncio.sleep(3600)  # кожну годину
            auth_manager.cleanup_expired_sessions()
        except Exception as exc:
            logger.error("Error in auth cleanup task: %s", exc)


# ===============================
# CLEANUP USER ESP ACCESS
# ===============================
def remove_user_from_all_esps(user_id: int):
    global esp_allowed_users

    for esp_id in list(esp_allowed_users.keys()):
        esp_allowed_users[esp_id].discard(user_id)

        if not esp_allowed_users[esp_id]:
            esp_allowed_users.pop(esp_id)


def remove_user_ws_subscriptions(user_id: int):
    from app.main import manager

    for ws in list(manager.connections.keys()):
        # websocket не знає user_id напряму
        # але можна зберегти його в ws.state
        if hasattr(ws, "user_id") and ws.user_id == user_id:
            manager.unsubscribe(ws)

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
app.include_router(auth.router)
app.include_router(api.router)
app.include_router(admin_api_router)
app.include_router(admin_users_api_router)
app.include_router(admin_pages_router)
app.include_router(admin_transactions_router)
app.include_router(admin_device_transactions_router)
app.include_router(websocket.router)
app.include_router(pages.router)