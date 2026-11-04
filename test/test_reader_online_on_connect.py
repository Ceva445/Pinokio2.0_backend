"""Czytnik jest online od chwili podłączenia, nie od pierwszego skanu.

Device() rodzi się z is_online=False, a register_device() podnosiło flagę tylko
dla urządzenia, które już znało. Nowe zostawało offline, więc
/auth/available-esps (filtruje po is_online) go nie pokazywał i manager słyszał
„Wybrane urządzenie jest niedostępne (offline)" przy czytniku, który trzymał
otwarte gniazdo. Po restarcie serwera dotyczyło to wszystkich czytników.
"""
import pytest

from managers.device_manager import DeviceManager


def test_nowy_czytnik_jest_online():
    dm = DeviceManager()
    dev = dm.register_device("E-1")

    assert dev.is_online is True
    assert dev.last_seen is not None
    assert "E-1" in dm.get_online_devices()


def test_powrot_po_rozlaczeniu_podnosi_flage():
    dm = DeviceManager()
    dm.register_device("E-1").mark_offline()
    assert dm.get_online_devices() == {}

    dm.register_device("E-1")
    assert "E-1" in dm.get_online_devices()


@pytest.mark.asyncio
async def test_available_esps_widzi_czytnik_bez_skanu(monkeypatch):
    """Lista na ekranie logowania — to z niej manager wybiera urządzenie."""
    import app.main as mainmod
    from routers.auth import available_esps

    dm = DeviceManager()
    dm.register_device("E-1")
    monkeypatch.setattr(mainmod, "device_manager", dm)
    monkeypatch.setattr(mainmod, "esp_watchers", {})

    lista = await available_esps()
    assert [p["id"] for p in lista] == ["E-1"]
    assert lista[0]["watched_by"] is None
