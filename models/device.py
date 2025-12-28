"""Моделі пристроїв"""
from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel


class DeviceData(BaseModel):
    """Дані пристрою"""
    timestamp: datetime
    data: Dict[str, Any]

    def dict(self, **kwargs):
        d = super().model_dump(**kwargs)
        d['timestamp'] = self.timestamp.isoformat()
        return d
    
    class Config:
        arbitrary_types_allowed = True


class Device:
    """Модель пристрою ESP32"""
    
    def __init__(self, device_id: str, name: Optional[str] = None):
        self.id = device_id
        self.name = name or f"ESP32-{device_id[-6:]}"
        self.latest_data: Optional[DeviceData] = None
        self.connected_at: Optional[datetime] = None
        self.last_seen: Optional[datetime] = None
        self.is_online: bool = False
        
    def update_data(self, data: Dict[str, Any]) -> None:
        """Оновити дані пристрою"""
        self.latest_data = DeviceData(
            timestamp=datetime.now(),
            data=data
        )
        self.last_seen = datetime.now()
        self.is_online = True
        
    def mark_offline(self) -> None:
        """Позначити пристрій як офлайн"""
        self.is_online = False
        
    def to_dict(self) -> Dict[str, Any]:
        """Перетворити пристрій у словник"""
        return {
            "id": self.id,
            "name": self.name,
            "is_online": self.is_online,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "latest_data": self.latest_data.dict() if self.latest_data else None
        }