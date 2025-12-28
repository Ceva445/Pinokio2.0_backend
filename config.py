"""Конфігурація додатку"""
from pathlib import Path

# Шляхи
BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR / "app"

STATIC_DIR = APP_DIR / "static"
INDEX_FILE = STATIC_DIR / "index.html"

# Типи повідомлень
MSG_UPDATE = "update"
MSG_ESP32_DATA = "esp32_data"
MSG_PING = "ping"
MSG_PONG = "pong"
MSG_DEVICE_UPDATE = "device_update"
MSG_DEVICE_LIST = "device_list"
MSG_DEVICE_REGISTERED = "device_registered"
MSG_DEVICE_REMOVED = "device_removed"
MSG_DEVICE_STATUS_UPDATE = "device_status_update"

# Налаштування логування
LOG_CONFIG = {
    "level": "INFO",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
}

# Налаштування пристроїв
DEVICE_CONFIG = {
    "timeout_minutes": 10,  # через скільки хвилин вважати пристрій офлайн
    "max_devices": 100  # максимальна кількість пристроїв
}