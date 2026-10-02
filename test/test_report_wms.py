"""Тести звіту «Ruchy WMS bez rejestracji».

Звіт відповідає на одне питання: хто працював у WMS, але не брав у нас
обладнання. Період беремо з самого файлу — від найранішого до найпізнішого
руху, щоб нічого не треба було вводити руками.
"""
import inspect
import json
from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest
from fastapi import HTTPException
from openpyxl import load_workbook

from app.dependencies.admin import require_manager_or_admin
from models.db_device import DeviceDB, DeviceType
from models.db_employee import EmployeeDB
from models.db_site import SiteDB
from models.db_transaction import TransactionDB, TransactionType
from routers.admin.report_wms import (
    Ruch,
    build_workbook,
    okno,
    parse_dstamp,
    parse_wms,
    wms_report,
    wms_report_xlsx,
    zbierz,
    zgrupuj,
)

pytestmark = pytest.mark.asyncio

TERAZ = datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)


def _temu(godzin: float) -> datetime:
    return TERAZ - timedelta(hours=godzin)


def _plik(wiersze) -> bytes:
    return json.dumps(wiersze).encode()


def _wiersz(login, code="Pick", moment=None):
    moment = moment or _temu(1)
    return {"login": login, "CODE": code,
            "DSTAMP": moment.strftime("%Y-%m-%d %H:%M:%S.%f") + " UTC"}


# ---------------------------------------------------------------------------
# Wejście z WMS
# ---------------------------------------------------------------------------
async def test_dstamp_z_koncowka_utc():
    """WMS pisze strefę słowem, czego fromisoformat nie rozumie."""
    moment = parse_dstamp("2026-10-01 04:00:58.000000 UTC")

    assert moment == datetime(2026, 10, 1, 4, 0, 58, tzinfo=timezone.utc)


async def test_dstamp_w_formacie_eksportu_z_wms():
    """Prawdziwy eksport: dwucyfrowy rok, przecinek, nanosekundy — i czas
    lokalny magazynu, nie UTC.

    Sprawdzone na produkcji: przy czytaniu jako czas lokalny 142 ze 149 ruchów
    wypada w chwili, gdy człowiek miał wydany sprzęt, a przy UTC tylko 72.
    """
    moment = parse_dstamp("26/10/02 12:49:55,778394000")

    assert moment.utcoffset() == timedelta(hours=2)            # CEST
    assert moment.astimezone(timezone.utc) == datetime(
        2026, 10, 2, 10, 49, 55, 778394, tzinfo=timezone.utc)


async def test_urwany_plik_z_eksportu_daje_sie_odczytac():
    """Eksport zaczyna się od ,"items": i kończy ]} — jako całość to nie jest
    poprawny JSON, a i tak trzeba go przyjąć."""
    tresc = (
        ',"items":\n'
        '[\n'
        '{"login":"P-STASIVR","code":"Replenish",'
        '"dstamp":"26\\/10\\/02 12:49:55,778394000"}\n'
        ']}'
    )

    ruchy = parse_wms(tresc.encode())

    assert [(r.login, r.code) for r in ruchy] == [("P-STASIVR", "Replenish")]


async def test_dstamp_bez_strefy_jest_utc():
    assert parse_dstamp("2026-10-01 04:00:58") == datetime(
        2026, 10, 1, 4, 0, 58, tzinfo=timezone.utc)


async def test_plik_wms_czyta_sie_w_calosci():
    ruchy = parse_wms(_plik([_wiersz("P-A"), _wiersz("P-B", "Receipt")]))

    assert [r.login for r in ruchy] == ["P-A", "P-B"]
    assert ruchy[1].code == "Receipt"


async def test_eksport_opakowany_w_obiekt():
    """Bywa, że eksport przychodzi jako {"rows": [...]}, a nie goła lista."""
    ruchy = parse_wms(json.dumps({"rows": [_wiersz("P-A")]}).encode())

    assert len(ruchy) == 1


async def test_zly_plik_konczy_sie_czytelnym_bledem():
    """Człowiek wgrywa plik ręcznie — pomyłka to nie powód na pięćsetkę."""
    with pytest.raises(HTTPException) as blad:
        parse_wms(b"to nie jest json")
    assert blad.value.status_code == 400

    with pytest.raises(HTTPException):
        parse_wms(_plik([{"cos": "innego"}]))


async def test_popsute_wiersze_nie_psuja_calego_pliku():
    ruchy = parse_wms(_plik([
        _wiersz("P-A"),
        {"login": "", "CODE": "Pick", "DSTAMP": "2026-10-01 04:00:00 UTC"},
        {"login": "P-C", "CODE": "Pick", "DSTAMP": "nie-data"},
    ]))

    assert [r.login for r in ruchy] == ["P-A"]


# ---------------------------------------------------------------------------
# Okres bierze się z pliku
# ---------------------------------------------------------------------------
async def test_okres_to_pierwszy_i_ostatni_ruch():
    ruchy = [Ruch("P-A", "Pick", _temu(2)), Ruch("P-B", "Pick", _temu(30)),
             Ruch("P-C", "Pick", _temu(9))]

    assert okno(ruchy) == (_temu(30), _temu(2))


async def test_caly_plik_wchodzi_do_analizy():
    """Nic nie wypada: zakres jest zdjęty z pliku, więc każdy ruch jest w nim."""
    ruchy = [Ruch("P-A", "Pick", _temu(2)), Ruch("P-B", "Pick", _temu(300))]
    od, do = okno(ruchy)

    assert all(od <= r.moment <= do for r in ruchy)


async def test_login_laczy_sie_bez_wzgledu_na_wielkosc_liter():
    pogrupowane = zgrupuj([Ruch("p-a", "Pick", TERAZ), Ruch("P-A", "Pick", TERAZ)])

    assert list(pogrupowane) == ["P-A"]
    assert len(pogrupowane["P-A"]) == 2


# ---------------------------------------------------------------------------
# Analiza
# ---------------------------------------------------------------------------
@pytest.fixture
async def magazyn(db_session):
    site = SiteDB(name="STOCK")
    db_session.add(site)
    await db_session.commit()

    ludzie = {
        # pobrał sprzęt w oknie — wszystko w porządku
        "zarejestrowany": EmployeeDB(wms_login="P-OK", first_name="Ola", last_name="Dobra",
                                     company="Profit", rfid="r-ok", site_id=site.id),
        # pracował, sprzętu nie pobrał
        "bez": EmployeeDB(wms_login="P-BRAK", first_name="Bogdan", last_name="Bez",
                          company="Profit", rfid="r-brak", site_id=site.id),
        # pobrał, ale wczoraj — poza oknem
        "wczoraj": EmployeeDB(wms_login="P-WCZORAJ", first_name="Wit", last_name="Stary",
                              company="Fortuna", rfid="r-wczoraj"),
    }
    db_session.add_all(ludzie.values())
    skaner = DeviceDB(name="TERM001", rfid="r-t1", serial_number="s1",
                      type=DeviceType.scanner)
    ludzie["skaner"] = skaner
    db_session.add(skaner)
    await db_session.commit()

    db_session.add_all([
        TransactionDB(timestamp=_temu(3), type=TransactionType.registered,
                      employee_id=ludzie["zarejestrowany"].id, device_id=skaner.id),
        TransactionDB(timestamp=_temu(26), type=TransactionType.registered,
                      employee_id=ludzie["wczoraj"].id, device_id=skaner.id),
        # zwrot w oknie to nie jest pobranie sprzętu
        TransactionDB(timestamp=_temu(2), type=TransactionType.unregistered,
                      employee_id=None, device_id=skaner.id),
    ])
    await db_session.commit()
    return ludzie


@pytest.fixture
def ruchy():
    return [
        Ruch("P-OK", "Pick", _temu(2)),
        Ruch("P-BRAK", "Pick", _temu(2)),
        Ruch("P-BRAK", "Pick", _temu(1)),
        Ruch("P-BRAK", "Marshal", _temu(0.5)),
        Ruch("P-WCZORAJ", "Receipt", _temu(4)),
        Ruch("MrComplete", "Marshal", _temu(1)),
        # poza oknem — nie liczy się wcale
        Ruch("P-DAWNO", "Pick", _temu(40)),
    ]


async def test_kto_pracowal_bez_rejestracji(db_session, magazyn, ruchy):
    raport = await zbierz(db_session, ruchy)

    assert [w["login"] for w in raport["not_registered"]] == ["P-BRAK"]


async def test_sprzet_w_rekach_zdejmuje_z_listy(db_session, magazyn, ruchy):
    raport = await zbierz(db_session, ruchy)

    assert "P-OK" not in [w["login"] for w in raport["not_registered"]]
    assert raport["totals"]["with_device"] == 2


async def test_sprzet_pobrany_przed_plikiem_tez_sie_liczy(db_session, magazyn, ruchy):
    """Sedno kryterium: zmiana nocna bierze skanery wieczorem, a eksport
    zaczyna się po północy. Rejestracji w pliku nie widać, a sprzęt jest.

    Bez tego raport na produkcji pokazywał 65 "winnych", z czego 58 trzymało
    skaner pobrany przed początkiem eksportu."""
    krotki = await zbierz(db_session, [r for r in ruchy if r.moment >= _temu(5)])

    assert "P-WCZORAJ" not in [w["login"] for w in krotki["not_registered"]]


async def test_zwrocony_sprzet_nie_kryje_pozniejszej_pracy(db_session, magazyn, ruchy):
    """Skaner oddany o 6:00 nie tłumaczy ruchu o 8:00."""
    from models.db_transaction import TransactionDB, TransactionType

    sprzet = magazyn["skaner"]
    db_session.add(TransactionDB(timestamp=_temu(3), type=TransactionType.unregistered,
                                 employee_id=None, device_id=sprzet.id))
    await db_session.commit()

    raport = await zbierz(db_session, [Ruch("P-WCZORAJ", "Pick", _temu(2))])

    assert [w["login"] for w in raport["not_registered"]] == ["P-WCZORAJ"]


async def test_nieznane_loginy_osobno(db_session, magazyn, ruchy):
    raport = await zbierz(db_session, ruchy)

    assert sorted(w["login"] for w in raport["unknown"]) == ["MrComplete", "P-DAWNO"]
    assert "MrComplete" not in [w["login"] for w in raport["not_registered"]]


async def test_wiersz_mowi_ile_pracy_i_jakiej(db_session, magazyn, ruchy):
    raport = await zbierz(db_session, ruchy)
    bogdan = raport["not_registered"][0]

    assert bogdan["moves"] == 3
    assert bogdan["moves_without"] == 3
    assert dict(bogdan["codes"]) == {"Pick": 2, "Marshal": 1}
    assert bogdan["company"] == "Profit"
    assert bogdan["site"] == "STOCK"
    assert bogdan["last_registration"] is None          # nigdy nie brał sprzętu


async def test_najwiecej_pracy_bez_sprzetu_na_gorze(db_session, magazyn, ruchy):
    raport = await zbierz(db_session, ruchy)
    ilosci = [w["moves_without"] for w in raport["not_registered"]]

    assert ilosci == sorted(ilosci, reverse=True)


async def test_liczby_zgadzaja_sie_z_plikiem(db_session, magazyn, ruchy):
    raport = await zbierz(db_session, ruchy)
    t = raport["totals"]

    assert t["rows_total"] == 7
    assert t["logins_in_window"] == 5
    assert t["not_registered"] + t["with_device"] + t["unknown"] == t["logins_in_window"]
    # Okres to rozpiętość pliku: od ruchu sprzed 40 godzin do tego sprzed pół.
    assert raport["hours"] == 39.5


async def test_krotszy_plik_zaweza_wynik(db_session, magazyn, ruchy):
    """Węższy eksport to węższy okres — i tylko ci, którzy w nim pracowali."""
    raport = await zbierz(db_session, [r for r in ruchy if r.moment >= _temu(1)])

    assert raport["totals"]["rows_total"] == 3
    assert [w["login"] for w in raport["not_registered"]] == ["P-BRAK"]


# ---------------------------------------------------------------------------
# Plik
# ---------------------------------------------------------------------------
async def test_plik_ma_dwa_arkusze_i_zakres(db_session, magazyn, ruchy):
    raport = await zbierz(db_session, ruchy)
    workbook = load_workbook(BytesIO(build_workbook(raport)))

    assert workbook.sheetnames == ["Bez sprzętu", "Nieznane loginy", "Zakres"]
    arkusz = workbook["Bez sprzętu"]
    assert arkusz["A1"].value == "Login WMS"
    assert arkusz["A2"].value == "P-BRAK"
    assert arkusz.max_row == len(raport["not_registered"]) + 1
    assert workbook["Nieznane loginy"]["A2"].value == "MrComplete"


async def test_plik_pisze_ze_ktos_nigdy_nie_bral_sprzetu(db_session, magazyn, ruchy):
    raport = await zbierz(db_session, ruchy)
    arkusz = load_workbook(BytesIO(build_workbook(raport)))["Bez sprzętu"]

    assert arkusz.cell(row=2, column=11).value == "nigdy"


# ---------------------------------------------------------------------------
# Dostęp
# ---------------------------------------------------------------------------
async def test_raport_dla_kierownika_i_admina():
    for endpoint in (wms_report, wms_report_xlsx):
        guard = inspect.signature(endpoint).parameters["user"].default.dependency
        assert guard is require_manager_or_admin, endpoint.__name__


async def test_oba_panele_rysuja_ten_sam_ekran():
    from pathlib import Path

    for strona in ("app/templates/admin/reports/wms.html",
                   "app/templates/manager/reports/wms.html"):
        assert "reports/wms_body.html" in Path(strona).read_text(encoding="utf-8")


async def test_raport_mowi_jaki_okres_opisuje(db_session, magazyn, ruchy):
    """Nikt nie wpisuje dat, więc raport musi sam powiedzieć, co obejmuje."""
    raport = await zbierz(db_session, ruchy)

    assert raport["from"].startswith("2026-09-29")      # ruch sprzed 40 godzin
    assert raport["to"].startswith("2026-10-01")
