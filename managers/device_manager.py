"""Менеджер пристроїв ESP32"""
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timedelta
from models.device import Device

logger = logging.getLogger(__name__)


class DeviceManager:
    """Керування пристроями ESP32"""
    
    def __init__(self, timeout_minutes: int = 5):
        self.devices: Dict[str, Device] = {}
        self.timeout_minutes = timeout_minutes
        
    def register_device(self, device_id: str, name: Optional[str] = None) -> Device:
        """Зареєструвати новий пристрій"""
        if device_id not in self.devices:
            device = Device(device_id, name)
            device.connected_at = datetime.now()
            self.devices[device_id] = device
            logger.info("Device registered: %s (%s)", device_id, device.name)
        else:
            device = self.devices[device_id]
            device.is_online = True
            device.connected_at = datetime.now()
            
        return device
    
    def update_device_data(self, device_id: str, data: dict) -> Device:
        """Оновити дані пристрою"""
        if device_id not in self.devices:
            device = self.register_device(device_id)
        else:
            device = self.devices[device_id]
            
        device.update_data(data)
        return device
    
    def get_device(self, device_id: str) -> Optional[Device]:
        """Отримати пристрій за ID"""
        return self.devices.get(device_id)
    
    def get_all_devices(self) -> Dict[str, Device]:
        """Отримати всі пристрої"""
        return self.devices
    
    def get_online_devices(self) -> Dict[str, Device]:
        """Отримати тільки онлайн пристрої"""
        return {did: device for did, device in self.devices.items() if device.is_online}
    
    def cleanup_offline_devices(self) -> Dict[str, Device]:
        """Видалити пристрої, які не подавали ознак життя"""
        offline_devices = {}
        cutoff_time = datetime.now() - timedelta(minutes=self.timeout_minutes)
        
        for device_id, device in list(self.devices.items()):
            if device.last_seen and device.last_seen < cutoff_time:
                device.mark_offline()
                offline_devices[device_id] = device
                logger.info("Device marked as offline: %s", device_id)
                
        return offline_devices
    
    def get_device_status(self, device_id: str) -> Dict[str, Any]:
        """Отримати статус пристрою"""
        device = self.get_device(device_id)
        if device:
            return {
                "status": "online" if device.is_online else "offline",
                "device": device.to_dict()
            }
        return {"status": "not_found"}
    
    def get_all_devices_status(self) -> Dict[str, Any]:
        """Отримати статус всіх пристроїв"""
        online = len(self.get_online_devices())
        total = len(self.devices)
        
        return {
            "total_devices": total,
            "online_devices": online,
            "offline_devices": total - online,
            "devices": {did: device.to_dict() for did, device in self.devices.items()}
        }