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
    from routers.auth import get_current_user
    try:
        user = await get_current_user(False)(websocket)
        if user:
            websocket.user_id = user["id"]
    except Exception as e:
        print("WS auth error:", e)

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


# ==========================================================================
# WEBSOCKET ДЛЯ ESP32 (постійне зʼєднання замість HTTP POST /api/data/{id})
# --------------------------------------------------------------------------
# ESP тримає один відкритий сокет і шле на кожен скан {"rfid": "..."}.
# Сервер проганяє через ту саму process_rfid() (спільна з HTTP) і відсилає
# назад ack {"type":"ack","status":...,"message":...} для beep-фідбека.
# ==========================================================================

@router.websocket("/ws/device/{device_id}")
async def esp_device_websocket(
    websocket: WebSocket,
    device_id: str,
    manager: ConnectionManager = Depends(get_manager),
    devices: DeviceManager = Depends(get_devices),
):
    from routers.api import process_rfid
    from db.session import async_session

    await websocket.accept()

    # Позначаємо пристрій онлайн і оновлюємо список у браузерних моніторах
    devices.register_device(device_id)
    await manager.broadcast_device_list()

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"type": "ack", "status": "error", "message": "invalid json"}
                )
                continue

            # Кожне повідомлення — своя короткоживуча DB-сесія.
            # event_suffix="_v2" → події йдуть у новий монітор /monitor2.
            async with async_session() as db:
                result = await process_rfid(
                    device_id, data, devices, manager, db, event_suffix="_v2"
                )

            # Відповідь назад на ESP (для beep success/error)
            await websocket.send_json(
                {
                    "type": "ack",
                    "status": result.get("status"),
                    "message": result.get("message"),
                }
            )

    except WebSocketDisconnect:
        device = devices.get_device(device_id)
        if device:
            device.mark_offline()
        await manager.broadcast_device_list()
