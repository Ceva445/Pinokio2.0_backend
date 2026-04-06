"""Конфігурація додатку"""
from pathlib import Path
from dotenv import load_dotenv
from fastapi.templating import Jinja2Templates

load_dotenv()

# Шляхи
BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR / "app"

STATIC_DIR = APP_DIR / "static"

TEMPLATES_DIR = BASE_DIR / "app" / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Налаштування логування
LOG_CONFIG = {
    "level": "INFO",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
}

# ===== СИСТЕМА КОНФІГУРАЦІЇ =====
# Ці значення є дефолтними. Актуальні значення завжди беруться з БД (таблиця system_config)
# якщо в БД немає значення - використовується дефолт

# Таймаути (вплив на UI)
ACCESS_TOKEN_EXPIRE_MINUTES = 30  # як довго токен залишається валідним
DEVICE_TIMEOUT_MINUTES = 5  # як довго пристрій вважається онлайн без оновлень
REGISTRATION_TIMEOUT_SECONDS = 7  # таймаут реєстрації пристрою
DEVICE_CLEANUP_INTERVAL_SECONDS = 300  # як часто перевіряти офлайн пристрої (5 хвилин)
AUTH_CLEANUP_INTERVAL_SECONDS = 3600  # як часто очищувати застарілі сесії (1 година)

# Довгі таймаути (вплив на UI - email оповіщення)
DEVICE_NOT_RETURNED_HOURS = 12  # скільки годин перед оповіщенням про не повернення

# Настройки реєстрації
ALLOW_REGISTRATION_WITHOUT_LOGIN = False  # дозволити реєстрацію користувачів без входу в систему
