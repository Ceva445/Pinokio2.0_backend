import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from managers.connection_manager import ConnectionManager
from managers.device_manager import DeviceManager

router = APIRouter()


def get_manager():
    from app.main import manager
    return manager


def get_devices():
    from app.main import device_manager
    return device_manager


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    manager: ConnectionManager = Depends(get_manager),
    devices: DeviceManager = Depends(get_devices),
):
    await manager.connect(websocket)
    await manager.broadcast_device_list()

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)

            if msg["command"] == "subscribe":
                device_id = msg["device_id"]
                manager.subscribe(websocket, device_id)

                # 🔥 КРИТИЧНО: відправити ОСТАННІ дані одразу
                device = devices.get_device(device_id)
                if device and device.latest_data:
                    await manager.send_json(websocket, {
                        "type": "esp32_data",
                        "device_id": device_id,
                        "data": device.latest_data.data,
                    })

            elif msg["command"] == "unsubscribe":
                manager.unsubscribe(websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
