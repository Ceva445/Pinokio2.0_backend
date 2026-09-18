"""Ślad sesji w logach: kto, którą sesją i dlaczego ją stracił.

Log dostępowy uvicorna pokazuje tylko adres proksy i ścieżkę — wszyscy
przychodzą z tego samego IP, więc przy dwóch osobach naraz nie da się
powiedzieć, czyj był 401. Tu każde zdarzenie niesie login i skrót tokenu,
a każda utrata sesji — powód.

Wszystko idzie jednym prefiksem, żeby dało się to wyciągnąć jednym grepem:

    docker logs pinokio-backend 2>&1 | grep SESSION

Tokenu nigdy nie wypisujemy — tylko 8 znaków jego skrótu SHA-256. To
wystarcza, żeby powiązać zdarzenia jednej sesji, a z logu nie da się już
nikogo podszyć.
"""
import hashlib
import logging

logger = logging.getLogger("pinokio.session")


def tag(token: str | None) -> str:
    if not token:
        return "-"
    return hashlib.sha256(token.encode()).hexdigest()[:8]


def owner(token: str | None) -> str:
    """Login właściciela tokenu — także wtedy, gdy sesji już nie ma w pamięci.

    Po unieważnieniu sesja znika z active_sessions, ale podpis tokenu dalej
    jest ważny, więc "sub" da się z niego odczytać.
    """
    if not token:
        return "-"
    from managers.auth_manager import auth_manager

    user = auth_manager.get_user_from_token(token)
    if user:
        return user.get("username") or "-"
    payload = auth_manager.decode_token(token)
    return (payload or {}).get("sub") or "?"


def path(request) -> str | None:
    """Ścieżka zapytania, jeśli da się ją odczytać."""
    return getattr(getattr(request, "url", None), "path", None)


def event(name: str, token: str | None = None, **fields) -> None:
    """Jedna linia: SESSION <zdarzenie> user=… tok=… i reszta pól.

    Nigdy nie rzuca wyjątku. Ten log stoi w samym środku logowania i
    sprawdzania sesji — jego błąd nie może nikogo wylogować.
    """
    try:
        parts = [f"user={fields.pop('user', None) or owner(token)}", f"tok={tag(token)}"]
        parts += [f"{key}={value}" for key, value in fields.items() if value is not None]
        logger.info("SESSION %s %s", name, " ".join(parts))
    except Exception:  # noqa: BLE001 — log ma milczeć, a nie psuć sesję
        logger.debug("session log failed for %s", name, exc_info=True)
