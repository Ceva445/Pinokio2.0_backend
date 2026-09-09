"""Тести ролі «obserwator».

Спостерігач заходить у панель адміністратора, але бачить там лише дашборд:
сприяту не видає і на монітор не потрапляє.

Найважливіше тут — не те, що в шаблоні немає кнопки. Право авторизувати видачу
береться з запису в `esp_allowed_users`, а той запис створює звичайний ендпоінт
підписки на зчитувач. Тому тести перевіряють саме прив'язку залежностей до
маршрутів, а не вигляд сторінки.
"""
import inspect

import pytest
from fastapi import HTTPException

from app.dependencies.admin import (
    forbid_observer,
    require_admin,
    require_admin_or_observer,
    require_dashboard_viewer,
    require_manager_or_admin,
)
from models.db_user import UserRole

ADMIN = {"id": 1, "username": "admin", "role": "admin"}
MANAGER = {"id": 2, "username": "kierownik", "role": "manager"}
OBSERVER = {"id": 3, "username": "obserwator", "role": "observer"}


def _allows(guard, user) -> bool:
    try:
        guard(current_user=user)
        return True
    except HTTPException:
        return False


def _depends_on(func, param_name="current_user"):
    """Яка залежність реально стоїть у сигнатурі ендпоінта."""
    return inspect.signature(func).parameters[param_name].default.dependency


# ---------------------------------------------------------------------------
# Роль існує і не ламає наявних
# ---------------------------------------------------------------------------
def test_observer_is_a_known_role():
    assert UserRole.observer.value == "observer"
    assert {r.value for r in UserRole} == {"admin", "manager", "observer"}


# ---------------------------------------------------------------------------
# Хто куди
# ---------------------------------------------------------------------------
def test_observer_enters_the_admin_panel():
    assert _allows(require_admin_or_observer, OBSERVER)
    assert _allows(require_admin_or_observer, ADMIN)
    # Кierownik має власну панель — сюди йому не треба.
    assert not _allows(require_admin_or_observer, MANAGER)


def test_observer_reads_the_dashboard():
    for user in (ADMIN, MANAGER, OBSERVER):
        assert _allows(require_dashboard_viewer, user), user["role"]


def test_observer_stays_out_of_the_rest_of_the_panel():
    """Решта екранів адмінки лишається під require_admin."""
    assert not _allows(require_admin, OBSERVER)
    assert not _allows(require_manager_or_admin, OBSERVER)


def test_forbid_observer_lets_the_others_through():
    assert not _allows(forbid_observer, OBSERVER)
    assert _allows(forbid_observer, ADMIN)
    assert _allows(forbid_observer, MANAGER)


# ---------------------------------------------------------------------------
# Головне: не може отримати право на видачу
# ---------------------------------------------------------------------------
def test_subscribing_to_a_reader_is_closed_for_observer():
    """Підписка на ESP кладе користувача в esp_allowed_users, а це і є дозвіл
    авторизувати видачу. Без цієї охорони «не видає сприят» трималося б лише
    на тому, що монітор йому не показують."""
    from routers.api import subscribe_esp

    assert _depends_on(subscribe_esp) is forbid_observer


def test_monitor_pages_reject_an_observer():
    from routers.pages import _block_observer

    with pytest.raises(HTTPException) as exc:
        _block_observer(OBSERVER)
    assert exc.value.status_code == 403

    # Адмін, кierownik і незалогінений гість монітор бачать як раніше.
    for user in (ADMIN, MANAGER, None):
        _block_observer(user)


def test_only_managers_bind_a_reader_at_login():
    """Прив'язка зчитувача при вході — умова саме на роль менеджера, а не
    «усі, крім адміна»; інакше спостерігач потрапив би в esp_allowed_users."""
    source = inspect.getsource(__import__("routers.auth", fromlist=["auth"]).login_form)

    assert "binds_reader = role == UserRole.manager.value" in source
    assert 'role != "admin"' not in source


# ---------------------------------------------------------------------------
# Дашборд справді відкритий, а не лише названий
# ---------------------------------------------------------------------------
def test_dashboard_endpoints_use_the_wider_guard():
    from routers.admin.api import get_dashboard, get_dashboard_devices, get_dashboard_employees

    for endpoint in (get_dashboard, get_dashboard_devices, get_dashboard_employees):
        assert _depends_on(endpoint, "user") is require_dashboard_viewer, endpoint.__name__


def test_admin_dashboard_page_admits_observer():
    from routers.admin.pages import admin_dashboard

    assert _depends_on(admin_dashboard) is require_admin_or_observer


def test_other_admin_endpoints_did_not_get_loosened():
    """Заміна залежності легко зачіпає сусідів — перевіряємо кілька опорних."""
    from routers.admin.api import create_device, get_devices, get_guests

    assert _depends_on(get_guests, "user") is require_manager_or_admin
    assert _depends_on(get_devices, "user") is require_admin
    assert _depends_on(create_device, "user") is require_admin
