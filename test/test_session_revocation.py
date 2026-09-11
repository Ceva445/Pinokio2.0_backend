"""Тести виходу з системи і примусового вилогування.

Дві діри, що зійшлися на одному користувачі:

1. Вихід сам вимагав живої сесії. Якщо токен уже протух або був відкликаний,
   `/auth/logout` віддавав 401, кнопка казала «Nie udało się wylogować», а
   cookie лишалась у браузері. Людина бачила екран залогіненого і не мала як
   із нього вийти.

2. Відкликання жило лише в памʼяті процесу: `revoked_tokens` і кеш сесій. Після
   рестарту бекенда (тобто після кожного деплою) вони порожні, а токен у
   браузері живе свої 12 годин. Виходило, що адмін не бачив людину як
   залогінену і не мав кого вилогувати, а та поверталась сама собою.
"""
import inspect
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from jose import jwt
from sqlalchemy import select

from managers.auth_manager import ALGORITHM, SECRET_KEY, auth_manager
from models.db_user import UserDB, UserRole
from routers.auth import get_current_user, logout
from routers.admin.api_users import force_logout_user

pytestmark = pytest.mark.asyncio


class _Response:
    def __init__(self):
        self.deleted = []

    def delete_cookie(self, key):
        self.deleted.append(key)


class _Request:
    def __init__(self, token=None):
        self.cookies = {"access_token": token} if token else {}


@pytest.fixture(autouse=True)
def czysta_pamiec():
    """Odwołania i sesje żyją w pamięci procesu i przeciekałyby między testami:
    token unieważniony w jednym teście jest bajt w bajt tym samym ciągiem w
    następnym, bo powstaje z tych samych danych."""
    from app.main import revoked_tokens

    revoked_tokens.clear()
    auth_manager.active_sessions.clear()
    yield
    revoked_tokens.clear()
    auth_manager.active_sessions.clear()


@pytest.fixture
async def manager_user(db_session):
    user = UserDB(first_name="Yuliia", last_name="Bobokhina",
                  username="P-BOBOKHINAY", password_hash="x",
                  role=UserRole.manager)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _token(username="P-BOBOKHINAY", issued_at=None, hours=12):
    now = issued_at or datetime.utcnow()
    return jwt.encode(
        {"sub": username, "iat": now, "exp": now + timedelta(hours=hours)},
        SECRET_KEY, algorithm=ALGORITHM,
    )


async def _resolve(db, token, required=True):
    return await get_current_user(required)(
        request=_Request(token), token=None, db=db
    )


# ---------------------------------------------------------------------------
# 1. Вихід має працювати завжди
# ---------------------------------------------------------------------------
async def test_logout_does_not_need_a_living_session():
    """Найважливіше: вихід — це прибирання, він не може вимагати того, що
    саме зникло."""
    source = inspect.getsource(logout)

    assert "get_current_user(False)" in source
    assert "Depends(get_current_user())" not in source


async def test_logout_clears_the_cookie_even_without_a_user():
    from app.main import revoked_tokens

    token = _token()
    response = _Response()

    result = await logout(
        request=_Request(token), response=response,
        current_user=None, token=None,
    )

    assert "access_token" in response.deleted
    assert token in revoked_tokens
    assert result["message"]


async def test_logout_also_revokes_the_token_it_was_given():
    from app.main import revoked_tokens

    token = _token("inny-user")
    await logout(
        request=_Request(token), response=_Response(),
        current_user=None, token=None,
    )

    assert token in revoked_tokens


# ---------------------------------------------------------------------------
# 2. Відкликання має пережити рестарт
# ---------------------------------------------------------------------------
async def test_token_issued_before_the_cutoff_is_dead(db_session, manager_user):
    """Саме той випадок, що на проді: памʼять процесу порожня після деплою,
    а токен у браузері ще живий."""
    token = _token(issued_at=datetime.utcnow() - timedelta(hours=1))

    manager_user.sessions_valid_from = datetime.now(timezone.utc)
    await db_session.commit()

    auth_manager.active_sessions.clear()   # rozruch procesu od zera

    with pytest.raises(HTTPException) as exc:
        await _resolve(db_session, token)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Session revoked"


async def test_token_issued_after_the_cutoff_works(db_session, manager_user):
    """Людина залогінилась наново — її не можна тримати за дверима."""
    manager_user.sessions_valid_from = datetime.now(timezone.utc) - timedelta(minutes=5)
    await db_session.commit()

    auth_manager.active_sessions.clear()

    user = await _resolve(db_session, _token())

    assert user["username"] == "P-BOBOKHINAY"


async def test_user_without_a_cutoff_is_untouched(db_session, manager_user):
    auth_manager.active_sessions.clear()

    user = await _resolve(db_session, _token())

    assert user["username"] == "P-BOBOKHINAY"


async def test_token_without_iat_falls_on_the_wrong_side(db_session, manager_user):
    """Токени, видані до цієї зміни, не мають iat — і мусять вважатись старими,
    інакше саме їх відкликати й не вийде."""
    now = datetime.utcnow()
    token = jwt.encode({"sub": "P-BOBOKHINAY", "exp": now + timedelta(hours=12)},
                       SECRET_KEY, algorithm=ALGORITHM)

    manager_user.sessions_valid_from = datetime.now(timezone.utc)
    await db_session.commit()
    auth_manager.active_sessions.clear()

    with pytest.raises(HTTPException) as exc:
        await _resolve(db_session, token)

    assert exc.value.status_code == 401


async def test_new_tokens_carry_their_issue_time():
    payload = auth_manager.decode_token(
        auth_manager.create_access_token(data={"sub": "ktos"})
    )

    assert "iat" in payload


# ---------------------------------------------------------------------------
# 3. Примусовий вилог адміном
# ---------------------------------------------------------------------------
async def test_force_logout_writes_the_cutoff(db_session, manager_user):
    await force_logout_user(user_id=manager_user.id, db=db_session, user=None)

    await db_session.refresh(manager_user)
    assert manager_user.sessions_valid_from is not None


async def test_force_logout_kills_a_token_that_survived_a_restart(db_session, manager_user):
    """Пройти весь шлях: токен був живий, адмін натиснув 🚪, токен помер."""
    token = _token()
    auth_manager.active_sessions.clear()

    assert (await _resolve(db_session, token))["username"] == "P-BOBOKHINAY"

    await force_logout_user(user_id=manager_user.id, db=db_session, user=None)
    auth_manager.active_sessions.clear()   # nawet po kolejnym restarcie

    with pytest.raises(HTTPException):
        await _resolve(db_session, token)


async def test_force_logout_on_a_stranger_is_refused(db_session, manager_user):
    with pytest.raises(HTTPException) as exc:
        await force_logout_user(user_id=9999, db=db_session, user=None)

    assert exc.value.status_code == 404


async def test_the_button_stays_next_to_logged_in_users_only():
    """Kнопка належить рядкам із живою сесією — так було і так має лишитись.

    Проблемою було не те, кому її видно, а те, що натискання нічого не давало:
    відкликання жило в памʼяті процесу і зникало при рестарті. Це лікує межа в
    базі, а не кнопка на кожному рядку."""
    from pathlib import Path

    admin_js = Path("app/static/js/admin/admin.js").read_text(encoding="utf-8")

    assert "u.is_logged_in ? `<button" in admin_js
    assert "forceLogout" in admin_js


# ---------------------------------------------------------------------------
# 4. Виштовхування з екрана
# ---------------------------------------------------------------------------
async def test_force_logout_tells_the_tab_to_leave(db_session, manager_user):
    """Те саме, що робить вилогування за простій: вкладка має сама піти на
    логін, а не лишатись на екрані, де людина була в ту мить."""
    from app.main import manager

    class _Ws:
        def __init__(self, user_id):
            self.user_id = user_id
            self.token = "token-tej-osoby"
            self.sent = []
            self.closed = False

        async def send_json(self, payload):
            self.sent.append(payload)

        async def close(self):
            self.closed = True

    ws = _Ws(manager_user.id)
    manager.connections[ws] = None
    try:
        await force_logout_user(user_id=manager_user.id, db=db_session, user=None)
    finally:
        manager.connections.pop(ws, None)

    # Po wyrzuceniu leci jeszcze zwykły broadcast listy urządzeń — liczy się to,
    # że wiadomość o wyjściu poszła pierwsza, zanim gniazdo zostało zamknięte.
    assert ws.sent[0] == {"type": "force_logout", "reason": "admin"}
    assert ws.closed


async def test_the_reason_has_its_own_wording():
    from pathlib import Path

    login_js = Path("app/static/js/login.js").read_text(encoding="utf-8")

    assert "admin:" in login_js


async def test_pages_without_a_monitor_watch_their_session():
    """Сторінки без WebSocket мусять питати про себе самі, інакше виштовхування
    дійшло б тільки до вкладки монітора."""
    from pathlib import Path

    base_html = Path("app/templates/base.html").read_text(encoding="utf-8")

    assert "SESSION_CHECK_MS" in base_html
    assert "/auth/me" in base_html
    assert 'location.href = "/login?reason=" + powod' in base_html
    # Powód bierzemy z odpowiedzi serwera, żeby zamknięta sesja nie meldowała
    # się jako wygasła.
    assert '"Session revoked"' in base_html
    # Повертаючись до вкладки людина дивиться на картинку з минулого —
    # тоді питаємо одразу, не чекаючи такту.
    assert "visibilitychange" in base_html


async def test_a_guest_is_never_pushed_to_login():
    """Головна і монітор відкриті й без входу. Вартовий не має права виганяти
    того, хто взагалі не заходив, — інакше сторінка сама себе замикає."""
    from pathlib import Path

    base_html = Path("app/templates/base.html").read_text(encoding="utf-8")

    assert "let sessionWasAlive = false;" in base_html
    assert "if (!sessionWasAlive) return;" in base_html
    # Прапорець ставиться лише після вдалого /auth/me.
    assert base_html.index("sessionWasAlive = true;") < base_html.index("async function watchSession")
