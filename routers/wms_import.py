"""Odbiór ruchów z WMS przysyłanych przez skrypt.

Skrypt na maszynie przy WMS odpytuje Oracle i wysyła wynik tutaj, a raport
"Praca w WMS bez pobranego sprzętu" pokazuje najnowszą paczkę sam z siebie.
Nikt nie musi robić eksportu ani wgrywać pliku ręcznie.

Logowania ten endpoint nie wymaga — skrypt chodzi bez człowieka i nie ma czym
się zalogować. Zamiast tego niesie wspólny klucz w nagłówku X-Pinokio-Key.
Bez ustawionego klucza po stronie serwera endpoint w ogóle nie działa: lepiej,
żeby import zamilkł, niż żeby każdy mógł tu wrzucić cokolwiek.
"""
import logging
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from models.db_wms_import import WmsImportDB
from routers.admin.report_wms import okno, parse_wms

router = APIRouter(prefix="/api", tags=["WMS"])

logger = logging.getLogger(__name__)

# Ten sam limit co przy wgrywaniu pliku ręcznie.
MAX_BODY_BYTES = 25 * 1024 * 1024


def _klucz_serwera() -> str:
    return (os.getenv("WMS_IMPORT_KEY") or "").strip()


async def zapisz_paczke(db: AsyncSession, surowe: bytes, source: str,
                        origin: str | None = None) -> WmsImportDB:
    """Sprawdza treść i zapisuje ją jako jedną paczkę."""
    ruchy = parse_wms(surowe)                 # zły format → 400 z wyjaśnieniem
    od, do = okno(ruchy)

    paczka = WmsImportDB(
        source=source,
        origin=(origin or "")[:100] or None,
        rows_total=len(ruchy),
        period_from=od,
        period_to=do,
        payload=[{"login": r.login, "code": r.code,
                  "dstamp": r.moment.isoformat()} for r in ruchy],
    )
    db.add(paczka)
    await db.commit()
    await db.refresh(paczka)
    return paczka


@router.post("/wms-import")
async def wms_import(
    request: Request,
    x_pinokio_key: str | None = Header(default=None),
    x_pinokio_origin: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Przyjmuje JSON z ruchami: {"items": [{login, code, dstamp}, …]}."""
    klucz = _klucz_serwera()
    if not klucz:
        logger.error("WMS_IMPORT_KEY nie jest ustawiony — import odrzucony")
        raise HTTPException(503, "Import z WMS nie jest skonfigurowany")

    if not x_pinokio_key or x_pinokio_key.strip() != klucz:
        logger.warning("Odrzucony import z WMS: zły klucz (origin=%s)", x_pinokio_origin)
        raise HTTPException(401, "Zły klucz")

    surowe = await request.body()
    if not surowe:
        raise HTTPException(400, "Puste żądanie")
    if len(surowe) > MAX_BODY_BYTES:
        raise HTTPException(413, "Paczka jest za duża (limit 25 MB)")

    paczka = await zapisz_paczke(db, surowe, source="push", origin=x_pinokio_origin)

    logger.info("Import z WMS: %d wierszy, %s – %s (origin=%s)",
                paczka.rows_total, paczka.period_from, paczka.period_to,
                paczka.origin)

    return {
        "status": "ok",
        "id": paczka.id,
        "rows": paczka.rows_total,
        "from": paczka.period_from.isoformat(),
        "to": paczka.period_to.isoformat(),
    }
