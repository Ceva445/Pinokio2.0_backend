from datetime import datetime, timedelta

class RegistrationSession:
    def __init__(self, employee):
        self.employee = employee
        self.started_at = datetime.now()

    def touch(self):
        self.started_at = datetime.now()

class RegistrationManager:
    def __init__(self, timeout_seconds: int = 60):
        self.sessions: dict[str, RegistrationSession] = {}
        self.timeout = timedelta(seconds=timeout_seconds)

    def start_or_replace(self, esp_id: str, employee):
        self.sessions[esp_id] = RegistrationSession(employee)

    def get(self, esp_id: str):
        session = self.sessions.get(esp_id)
        if not session:
            return None
        if datetime.now() - session.started_at > self.timeout:
            self.sessions.pop(esp_id, None)
            return None
        return session

    def refresh(self, esp_id: str):
        session = self.sessions.get(esp_id)
        if session:
            session.touch()

    def end(self, esp_id: str):
        self.sessions.pop(esp_id, None)