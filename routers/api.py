from typing import Dict, Any
from fastapi import APIRouter, Depends
from managers.connection_manager import ConnectionManager
from managers.device_manager import DeviceManager

router = APIRouter(prefix="/api", tags=["API"])


def get_manager():
    from app.main import manager
    return manager


def get_devices():
    from app.main import device_manager
    return device_manager


@router.post("/data/{device_id}")
async def receive_esp32_data(
    device_id: str,
    data: Dict[str, Any],
    devices: DeviceManager = Depends(get_devices),
    manager: ConnectionManager = Depends(get_manager),
):
    device = devices.update_device_data(device_id, data)

    # 🔥 КРИТИЧНО: оновити список пристроїв для ВСІХ клієнтів
    await manager.broadcast_device_list()

    # 🔥 Відправити live-дані ТІЛЬКИ підписнику
    await manager.broadcast_device_data(
        device_id,
        {
            "type": "esp32_data",
            "device_id": device_id,
            "data": data,
        },
    )

    return {"status": "ok"}
