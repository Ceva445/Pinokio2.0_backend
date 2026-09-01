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

    # Аутентифікація WS через cookie-токен (надійно)
    from managers.auth_manager import auth_manager
    token = websocket.cookies.get("access_token")
    user = auth_manager.get_user_from_token(token) if token else None
    websocket.token = token
    websocket.app_user = user      # не 'user' — це read-only property Starlette
    if user:
        websocket.user_id = user["id"]

    is_admin = bool(user) and user.get("role") == "admin"

    # Менеджер: авто-підписка на його прив'язаний ESP (без перемикання)
    if user and not is_admin:
        from app.main import esp_watchers
        for did, w in esp_watchers.items():
            if w.get("token") == token:
                manager.subscribe(websocket, did)
                device = devices.get_device(did)
                if device and device.latest_data:
                    await manager.send_json(websocket, {
                        "type": "esp32_data",
                        "device_id": did,
                        "data": device.latest_data.data,
                    })
                break

    await manager.broadcast_device_list()

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)

            # Менеджер прив'язаний до одного ESP → ігноруємо його subscribe/unsubscribe
            if user is not None and not is_admin:
                continue

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
        # Менеджер закрив вкладку → виловлюємо: звільняємо ESP + гасимо токен
        _u = getattr(websocket, "app_user", None)
        if _u and _u.get("role") != "admin":
            tok = getattr(websocket, "token", None)
            if tok:
                from app.main import release_esp_for_token, revoked_tokens
                release_esp_for_token(tok)
                revoked_tokens.add(tok)
                auth_manager.remove_session(tok)
                await manager.broadcast_device_list()


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
    import asyncio
    from datetime import datetime
    from routers.api import process_rfid
    from db.session import async_session

    await websocket.accept()

    # Позначаємо пристрій онлайн і оновлюємо список у браузерних моніторах
    devices.register_device(device_id)
    await manager.broadcast_device_list()

    # Keepalive: поки WS живий (живлення+інтернет) — тримаємо last_seen свіжим,
    # щоб cleanup_offline_devices не зняв девайс офлайн за простій.
    async def _keepalive():
        try:
            while True:
                await asyncio.sleep(60)
                dev = devices.get_device(device_id)
                if dev:
                    dev.last_seen = datetime.now()
                    dev.is_online = True
        except asyncio.CancelledError:
            pass

    ka_task = asyncio.create_task(_keepalive())

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
        pass
    finally:
        ka_task.cancel()
        device = devices.get_device(device_id)
        if device:
            device.mark_offline()
        await manager.broadcast_device_list()
