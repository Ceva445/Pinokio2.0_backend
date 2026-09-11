"""Тести поведінки при 401.

Токен живе 12 годин, а сесія кierownika зникає ще й при закритті вкладки
монітора та після простою. Коли це ловило відкриту сторінку, людина бачила на
весь екран `{"detail":"Session revoked"}` — правду, але марну.

Сторінка має вести на вхід, а fetch із панелі — і далі отримувати 401, інакше
скрипти замість помилки розбирали б HTML сторінки логіну.
"""
import pytest
from fastapi import status
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.main import _ERROR_REASONS, _LOGOUT_REASONS, page_error_goes_to_login

pytestmark = pytest.mark.asyncio


class _Url:
    def __init__(self, path):
        self.path = path


class _Request:
    """Мінімум, якого торкається хендлер."""

    def __init__(self, path="/admin/transactions", **headers):
        self.headers = {k.replace("_", "-"): v for k, v in headers.items()}
        self.url = _Url(path)
        self.method = "GET"


HTML = {"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
JSON = {"accept": "application/json"}


async def _handle(exc, path="/admin/transactions", **headers):
    return await page_error_goes_to_login(_Request(path=path, **headers), exc)


def _unauthorized(detail):
    return StarletteHTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


# ---------------------------------------------------------------------------
# Сторінка
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("detail, reason", [
    ("Session revoked", "revoked"),
    ("Invalid authentication credentials", "expired"),
    ("Not authenticated", "expired"),
    ("User not found or inactive", "inactive"),
])
async def test_page_goes_to_login_with_a_reason(detail, reason):
    response = await _handle(_unauthorized(detail), **HTML)

    assert response.status_code == 303
    assert response.headers["location"] == f"/login?reason={reason}"


async def test_unknown_detail_still_lands_on_login():
    """Новий текст помилки не має повертати користувача до JSON на екрані."""
    response = await _handle(_unauthorized("Cos zupelnie nowego"), **HTML)

    assert response.status_code == 303
    assert response.headers["location"] == "/login?reason=expired"


async def test_every_reason_is_known_to_the_login_screen():
    """Кожна причина мусить мати свій підпис у login.js, інакше людина побачить
    голе «Zostałeś wylogowany» без пояснення."""
    from pathlib import Path

    login_js = Path("app/static/js/login.js").read_text(encoding="utf-8")

    for reason in set(_LOGOUT_REASONS.values()):
        assert f"{reason}:" in login_js, reason


# ---------------------------------------------------------------------------
# Запити скриптів
# ---------------------------------------------------------------------------
async def test_fetch_still_gets_json():
    """Панель показує свою помилку в таблиці — їй потрібен 401, не редирект."""
    response = await _handle(_unauthorized("Session revoked"), **JSON)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert b"Session revoked" in response.body


async def test_xhr_marked_request_gets_json_even_asking_for_html():
    response = await _handle(
        _unauthorized("Session revoked"),
        accept=HTML["accept"], x_requested_with="XMLHttpRequest"
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# Решта помилок — теж на логін, бо йшлося саме про білий екран
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("code, reason", [
    (403, "forbidden"),
    (404, "notfound"),
    (400, "error"),
    (409, "error"),
    (500, "error"),
])
async def test_any_page_error_lands_on_login(code, reason):
    """Білий екран із JSON не має лишитись у жодному коді помилки."""
    exc = StarletteHTTPException(status_code=code, detail="cokolwiek")

    response = await _handle(exc, **HTML)

    assert response.status_code == 303
    assert response.headers["location"] == f"/login?reason={reason}"


async def test_login_itself_does_not_loop():
    """Якби посипалась сама сторінка логіну, редирект на неї ж крутив би
    браузер по колу — тоді краще віддати помилку як є."""
    exc = StarletteHTTPException(status_code=500, detail="cokolwiek")

    response = await _handle(exc, path="/login", **HTML)

    assert response.status_code == 500


async def test_error_reasons_are_known_to_the_login_screen():
    from pathlib import Path

    login_js = Path("app/static/js/login.js").read_text(encoding="utf-8")

    for reason in set(_ERROR_REASONS.values()) | {"error"}:
        assert f"{reason}:" in login_js, reason
