import logging
from typing import Dict, Any, Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self, device_manager):
        self.device_manager = device_manager
        self.connections: Dict[WebSocket, Optional[str]] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections[websocket] = None

    def disconnect(self, websocket: WebSocket):
        self.connections.pop(websocket, None)

    def subscribe(self, websocket: WebSocket, device_id: str):
        self.connections[websocket] = device_id
        logger.info("Subscribed to %s", device_id)

    def unsubscribe(self, websocket: WebSocket):
        self.connections[websocket] = None
        logger.info("Unsubscribed")

    async def send_json(self, websocket: WebSocket, payload: Dict[str, Any]):
        await websocket.send_json(payload)

    async def broadcast_device_list(self):
        status = self.device_manager.get_all_devices_status()
        # додаємо, хто зараз «слідкує» за кожним ESP (для вибору/підсвітки в моніторі)
        try:
            from app.main import esp_watchers
            for did, dev in status.get("devices", {}).items():
                w = esp_watchers.get(did)
                dev["watched_by"] = w.get("username") if w else None
        except Exception:
            pass
        payload = {"type": "device_list", "data": status}
        for ws in list(self.connections.keys()):
            await ws.send_json(payload)

    async def broadcast_device_data(self, device_id: str, payload: Dict[str, Any]):
        for ws, subscribed in self.connections.items():
            if subscribed == device_id:
                await ws.send_json(payload)

    async def broadcast_to_all(self, message_type: str, data: Dict[str, Any]):
        payload = {
            "type": message_type,
            "data": data
        }

        disconnected = []

        for ws in list(self.connections.keys()):
            try:
                await ws.send_json(payload)
            except Exception as exc:
                logger.warning("WebSocket error, removing connection: %s", exc)
                disconnected.append(ws)

        # Очистка мертвих з'єднань
        for ws in disconnected:
            self.disconnect(ws)