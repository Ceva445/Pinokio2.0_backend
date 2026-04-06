from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)

class RegistrationSession:
    def __init__(self, employee):
        self.employee = employee
        self.started_at = datetime.now(timezone.utc)

    def touch(self):
        self.started_at = datetime.now(timezone.utc)

class RegistrationManager:
    def __init__(self, timeout_seconds: int = 7):
        self.sessions: dict[str, RegistrationSession] = {}
        self.timeout = timedelta(seconds=timeout_seconds)

    def update_timeout(self, timeout_seconds: int):
        """Оновити таймаут для реєстрації"""
        self.timeout = timedelta(seconds=timeout_seconds)
        logger.info(f"Registration timeout updated to {timeout_seconds} seconds")

    def start_or_replace(self, esp_id: str, employee):
        self.sessions[esp_id] = RegistrationSession(employee)

    def get(self, esp_id: str):
        session = self.sessions.get(esp_id)
        if not session:
            return None
        if datetime.now(timezone.utc) - session.started_at > self.timeout:
            self.sessions.pop(esp_id, None)
            return None
        return session

    def refresh(self, esp_id: str):
        session = self.sessions.get(esp_id)
        if session:
            session.touch()

    def end(self, esp_id: str):
        self.sessions.pop(esp_id, None)

    def cleanup_expired(self) -> int:
        now = datetime.now(timezone.utc)
        expired_keys = [
            esp_id
            for esp_id, session in self.sessions.items()
            if now - session.started_at > self.timeout + timedelta(seconds=1)
        ]

        for esp_id in expired_keys:
            self.sessions.pop(esp_id, None)

        return len(expired_keys)