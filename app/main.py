"""Головний файл додатку"""
import logging
import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from config import STATIC_DIR, LOG_CONFIG
from managers.connection_manager import ConnectionManager
from managers.device_manager import DeviceManager
from routers import api, email_agent, pages, websocket, auth
from fastapi.middleware.cors import CORSMiddleware
from managers.registration_manager import RegistrationManager
from managers.auth_manager import auth_manager
from managers.config_manager import config_manager
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
import sys
from routers.admin.api import router as admin_api_router
from routers.admin.api_users import router as admin_users_api_router
from routers.admin.api_system_config import router as admin_system_config_router
from routers.admin.pages import router as admin_pages_router
from routers.admin.admin_transactions import router as admin_transactions_router
from routers.admin.admin_device_transactions import router as admin_device_transactions_router
from routers.manager.pages import router as manager_pages_router
from routers.manager.api_transactions import router as manager_transactions_router


# Налаштування логування
logging.basicConfig(**LOG_CONFIG)
logger = logging.getLogger(__name__)

# Глобальні менеджери
device_manager = DeviceManager(timeout_minutes=5)
manager = ConnectionManager(device_manager)
registration_manager = RegistrationManager(timeout_seconds=7)
esp_allowed_users: dict[str, set[int]] = {}

# Глобальні конфіги (оновлюються динамічно при змінах)
system_config = {
    "device_cleanup_interval_seconds": 300,
    "auth_cleanup_interval_seconds": 3600,
    "device_not_returned_hours": 12,
}

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def load_config_on_startup():
    """Завантажити конфіги з БД при старті та оновити менеджери"""
    global system_config
    try:
        from db.session import engine
        from sqlalchemy.ext.asyncio import async_sessionmaker
        
        async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session_factory() as db:
            config = await config_manager.get_config(db)
            
            # Оновити менеджери з конфігами з БД
            if "device_timeout_minutes" in config:
                device_manager.update_timeout(config["device_timeout_minutes"])
                logger.info(f"Device timeout set to {config['device_timeout_minutes']} minutes")
            
            if "registration_timeout_seconds" in config:
                registration_manager.update_timeout(config["registration_timeout_seconds"])
                logger.info(f"Registration timeout set to {config['registration_timeout_seconds']} seconds")
            
            # Оновити глобальні конфіги
            if "device_cleanup_interval_seconds" in config:
                system_config["device_cleanup_interval_seconds"] = config["device_cleanup_interval_seconds"]
            if "auth_cleanup_interval_seconds" in config:
                system_config["auth_cleanup_interval_seconds"] = config["auth_cleanup_interval_seconds"]
            if "device_not_returned_hours" in config:
                system_config["device_not_returned_hours"] = config["device_not_returned_hours"]
            
            logger.info("Configuration loaded from database successfully")
    except Exception as e:
        logger.warning(f"Could not load config from database on startup: {e}")
        logger.info("Using default configuration values")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ESP32 Multi-Device Monitor started")
    
    # Завантажити конфіги з БД при старті
    await load_config_on_startup()
    
    cleanup_task = asyncio.create_task(cleanup_offline_devices())
    auth_cleanup_task = asyncio.create_task(cleanup_auth_sessions())
    registration_cleanup_task = asyncio.create_task(cleanup_registration_sessions())
    
    yield
    
    for task in [cleanup_task, auth_cleanup_task, registration_cleanup_task]:
        task.cancel()
    
    for task in [cleanup_task, auth_cleanup_task, registration_cleanup_task]:
        try:
            await task
        except asyncio.CancelledError:
            pass

    logger.info("ESP32 Multi-Device Monitor stopped")


async def cleanup_offline_devices():
    """Фонова задача для очищення офлайн пристроїв"""
    while True:
        try:
            interval = system_config.get("device_cleanup_interval_seconds", 300)
            await asyncio.sleep(interval)
            offline_devices = device_manager.cleanup_offline_devices()
            if offline_devices:
                # Сповістити клієнтів про зміни статусу
                await manager.broadcast_device_list()
        except Exception as exc:
            logger.error("Error in cleanup task: %s", exc)


async def cleanup_auth_sessions():
    while True:
        try:
            interval = system_config.get("auth_cleanup_interval_seconds", 3600)
            await asyncio.sleep(interval)
            auth_manager.cleanup_expired_sessions()
        except Exception as exc:
            logger.error("Error in auth cleanup task: %s", exc)


async def cleanup_registration_sessions():
    logger.info("Registration cleanup task started")
    
    while True:
        try:
            await asyncio.sleep(60)  # інтервал
            
            deleted = registration_manager.cleanup_expired()
            
            if deleted:
                logger.info(f"Removed {deleted} expired sessions")
                
        except Exception as exc:
            logger.error("Error in registration cleanup task: %s", exc)

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
app.include_router(admin_system_config_router)
app.include_router(admin_pages_router)
app.include_router(admin_transactions_router)
app.include_router(admin_device_transactions_router)
app.include_router(manager_pages_router)
app.include_router(manager_transactions_router)
app.include_router(websocket.router)
app.include_router(pages.router)
app.include_router(email_agent.router)