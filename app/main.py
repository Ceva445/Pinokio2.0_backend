"""Головний файл додатку"""
import logging
import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from config import STATIC_DIR, LOG_CONFIG
from managers.connection_manager import ConnectionManager
from managers.device_manager import DeviceManager
from routers import api, email_agent, pages, websocket, auth, firmware
from fastapi.middleware.cors import CORSMiddleware
from managers.registration_manager import RegistrationManager
from managers.auth_manager import auth_manager
from managers.config_manager import config_manager
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
import sys
from routers.admin.api import router as admin_api_router
from routers.admin.api_users import router as admin_users_api_router
from routers.admin.device_statuses import router as admin_device_statuses_router
from routers.admin.api_system_config import router as admin_system_config_router
from routers.admin.api_firmware import router as admin_firmware_router
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
# --- Вибір ESP при логіні (ексклюзивна прив'язка, тільки менеджери) ---
esp_watchers: dict[str, dict] = {}   # device_id → {"user_id", "username", "token"}
revoked_tokens: set[str] = set()     # токени, «виловлені» на закритті вкладки (WS-розрив)
# Розрив WS ≠ закриття вкладки (reload/перехід теж рвуть сокет), тому логаут
# відкладаємо: якщо той самий токен перепідключився за LOGOUT_GRACE_SECONDS —
# скасовуємо. Реально розлогінюємо тільки якщо вкладку закрили назовсім.
LOGOUT_GRACE_SECONDS = 15
pending_logouts: dict[str, object] = {}   # token → asyncio.Task відкладеного логауту

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def load_config_on_startup():
    """Завантажити конфіги з БД при старті та оновити менеджери"""
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
    employee_expiration_task = asyncio.create_task(do_employee_expired_if_needed())
    email_scheduler_task = asyncio.create_task(email_notification_scheduler())

    yield

    _bg_tasks = [cleanup_task, auth_cleanup_task, registration_cleanup_task, employee_expiration_task, email_scheduler_task]
    for task in _bg_tasks:
        task.cancel()

    for task in _bg_tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass

    logger.info("ESP32 Multi-Device Monitor stopped")


async def do_employee_expired_if_needed():
    """Фонова задача для перевірки та помічення розенаділених карток як експірованих"""
    from db.session import engine
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlalchemy import select
    from datetime import datetime, timezone, timedelta
    from models.db_guest import DBGuest
    from models.db_employee import EmployeeDB
    
    async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    while True:
        try:
            # Брати інтервал з БД через конфіг-менеджер (з кешуванням)
            async with async_session_factory() as db:
                config = await config_manager.get_config(db)
                temporary_card_duration_hours = config.get("temporary_card_duration_hours", 72)
                
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                cutoff_time = now - timedelta(hours=temporary_card_duration_hours)
                
                # Отримати тільки експірованих гостей з БД (last_used_at < cutoff)
                expired_guests = await db.execute(
                    select(DBGuest).where(
                        DBGuest.last_used_at.isnot(None),
                        DBGuest.last_used_at < cutoff_time
                    )
                )
                expired_guests_list = expired_guests.scalars().all()
                
                # Зібрати RFIDs експірованих гостей
                expired_rfids = [guest.rfid for guest in expired_guests_list]
                
                # Якщо є експіровані, оновити всіх працівників одним запитом (уникнути N+1)
                if expired_rfids:
                    employees_result = await db.execute(
                        select(EmployeeDB).where(
                            EmployeeDB.rfid.in_(expired_rfids),
                            EmployeeDB.expired == False
                        )
                    )
                    employees = employees_result.scalars().all()
                    
                    for employee in employees:
                        employee.expired = True
                        logger.info(f"Employee {employee.first_name} {employee.last_name} marked as expired (temporary card duration exceeded)")
                    
                    await db.commit()
            
            # Перевіряти кожні 30 хвилин
            await asyncio.sleep(30 * 60)
            
        except Exception as exc:
            logger.error("Error in employee expiration check task: %s", exc)
            # Не дозволити crash, спробувати знову через деякий час
            await asyncio.sleep(60)


async def cleanup_offline_devices():
    """Фонова задача для очищення офлайн пристроїв"""
    from db.session import engine
    from sqlalchemy.ext.asyncio import async_sessionmaker
    
    async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    while True:
        try:
            # Брати інтервал з БД через конфіг-менеджер (з кешуванням на 5 хвилин)
            async with async_session_factory() as db:
                config = await config_manager.get_config(db)
                interval = config.get("device_cleanup_interval_seconds", 300)
            
            await asyncio.sleep(interval)
            offline_devices = device_manager.cleanup_offline_devices()
            if offline_devices:
                # Сповістити клієнтів про зміни статусу
                await manager.broadcast_device_list()
        except Exception as exc:
            logger.error("Error in cleanup task: %s", exc)


async def cleanup_auth_sessions():
    from db.session import engine
    from sqlalchemy.ext.asyncio import async_sessionmaker
    
    async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    while True:
        try:
            # Брати інтервал з БД через конфіг-менеджер (з кешуванням на 5 хвилин)
            async with async_session_factory() as db:
                config = await config_manager.get_config(db)
                interval = config.get("auth_cleanup_interval_seconds", 3600)
            
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


async def email_notification_scheduler():
    """Планувальник email-нотифікацій про неповернені пристрої.

    Тикає кожні 20с; коли час (Europe/Warsaw) збігається з одним із
    email_send_times у конфізі (адмін задає в панелі) — кличе розсилку.
    Захист від подвійної відправки в межах хвилини через last_fired.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from db.session import engine

    tz = ZoneInfo("Europe/Warsaw")
    async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    last_fired = None

    logger.info("Email notification scheduler started")

    while True:
        try:
            now = datetime.now(tz)
            hhmm = now.strftime("%H:%M")
            minute_key = now.strftime("%Y-%m-%d %H:%M")

            if minute_key != last_fired:
                async with async_session_factory() as db:
                    config = await config_manager.get_config(db)
                    enabled = config.get("email_notifications_enabled", True)

                    # Окремі розклади: будні (пн-пт) / субота / неділя
                    weekday = now.weekday()  # Mon=0 ... Sat=5, Sun=6
                    if weekday == 5:
                        times_str = config.get("email_send_times_saturday")
                    elif weekday == 6:
                        times_str = config.get("email_send_times_sunday")
                    else:
                        times_str = config.get("email_send_times")

                    times = [t.strip() for t in str(times_str or "").split(",") if t.strip()]

                    if enabled and hhmm in times:
                        last_fired = minute_key
                        from routers.email_agent import run_email_notifications
                        result = await run_email_notifications(db)
                        logger.info(
                            "Scheduled email notifications fired at %s (Warsaw): %s",
                            hhmm, result
                        )

            await asyncio.sleep(20)
        except Exception as exc:
            logger.error("Error in email notification scheduler: %s", exc)
            await asyncio.sleep(30)


# ===============================
# ESP SELECTION (login-bound tracking)
# ===============================
def bind_esp(device_id: str, user: dict, token: str):
    """Прив'язати менеджера (за токеном сесії) до ESP: ексклюзивно."""
    esp_watchers[device_id] = {
        "user_id": user["id"],
        "username": user["username"],
        "token": token,
    }
    esp_allowed_users.setdefault(device_id, set()).add(user["id"])


def release_esp_for_token(token: str) -> str | None:
    """Зняти прив'язку за токеном (при виловлюванні/розриві). Повертає device_id."""
    for device_id, w in list(esp_watchers.items()):
        if w.get("token") == token:
            esp_watchers.pop(device_id, None)
            uid = w.get("user_id")
            if uid is not None and device_id in esp_allowed_users:
                esp_allowed_users[device_id].discard(uid)
                if not esp_allowed_users[device_id]:
                    esp_allowed_users.pop(device_id, None)
            return device_id
    return None


def esp_watcher_of(device_id: str) -> dict | None:
    return esp_watchers.get(device_id)


# ===============================
# CLEANUP USER ESP ACCESS
# ===============================
def remove_user_from_all_esps(user_id: int):
    global esp_allowed_users

    for esp_id in list(esp_allowed_users.keys()):
        esp_allowed_users[esp_id].discard(user_id)

        if not esp_allowed_users[esp_id]:
            esp_allowed_users.pop(esp_id)

    # також зняти watcher-прив'язку цього користувача
    for device_id, w in list(esp_watchers.items()):
        if w.get("user_id") == user_id:
            esp_watchers.pop(device_id, None)


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


@app.middleware("http")
async def no_cache_middleware(request, call_next):
    """Забороняємо кешування (браузер + Cloudflare) для всіх відповідей —
    щоб оновлення HTML/CSS/JS зʼявлялись одразу, без застарілого кешу."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# Монтування статичних файлів
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Підключення маршрутів
app.include_router(auth.router)
app.include_router(api.router)
app.include_router(firmware.router)
app.include_router(admin_api_router)
app.include_router(admin_firmware_router)
app.include_router(admin_device_statuses_router)
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