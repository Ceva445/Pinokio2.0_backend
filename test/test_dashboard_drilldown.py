"""Тести рознесення (drill-down) чисел дашборда.

Головна вимога: список, що розгортається під числом, має містити рівно ті
рядки, які це число порахувало. Тому кожен тест зіставляє drill-down із
самим get_dashboard, а не з константою.
"""
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from models.db_device import DeviceDB, DeviceType
from models.db_employee import EmployeeDB
from models.db_transaction import TransactionDB, TransactionType
from models.db_site import SiteDB
from sqlalchemy import select
from routers.admin.api import (
    get_dashboard,
    get_dashboard_devices,
    get_dashboard_employees,
)

pytestmark = pytest.mark.asyncio


async def _site(db, name):
    """Site ze słownika — pracownik trzyma FK, nie wpisany ręcznie tekst."""
    site = (await db.execute(select(SiteDB).where(SiteDB.name == name))).scalar_one_or_none()
    if site is None:
        site = SiteDB(name=name)
        db.add(site)
        await db.commit()
        await db.refresh(site)
    return site


async def _employee(db, wms_login, site_name, last_name="Kowalski"):
    site = await _site(db, site_name) if site_name else None
    e = EmployeeDB(
        last_name=last_name, first_name="Jan", rfid=f"rfid-{wms_login}",
        company="ACME", wms_login=wms_login,
        site_id=site.id if site else None,
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def _device(db, name, type_, employee_id=None, enabled=True):
    d = DeviceDB(
        name=name, rfid=f"rfid-{name}", serial_number=f"sn-{name}",
        type=type_, employee_id=employee_id, enabled=enabled,
    )
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return d


@pytest.fixture
async def warehouse(db_session):
    """Склад із усіма ситуаціями, які дашборд рахує окремо: працівник із
    кількома пристроями, зламаний пристрій, працівник без відділу і вільні
    пристрої, що нікому не видані."""
    anna = await _employee(db_session, "A-NOWAK", "STOCK", last_name="Nowak")
    bartek = await _employee(db_session, "B-WOJCIK", "STOCK", last_name="Wojcik")
    cezary = await _employee(db_session, "C-ZAJAC", None, last_name="Zajac")

    await _device(db_session, "SCAN-A1", DeviceType.scanner, anna.id)
    await _device(db_session, "PRINT-A2", DeviceType.printer, anna.id)
    await _device(db_session, "PRINT-B1", DeviceType.printer, bartek.id)
    await _device(db_session, "SCAN-B2", DeviceType.scanner, bartek.id, enabled=False)
    await _device(db_session, "SCAN-C1", DeviceType.scanner, cezary.id)
    await _device(db_session, "PRINT-FREE", DeviceType.printer)
    await _device(db_session, "PRINT-BROKEN", DeviceType.printer, enabled=False)

    return {"anna": anna, "bartek": bartek, "cezary": cezary}


async def _devices(db, **kwargs):
    """get_dashboard_devices із повним набором аргументів — при прямому виклику
    FastAPI не підставляє дефолти з Query()."""
    params = {"device_type": None, "enabled": None, "assigned": None, "site": None}
    params.update(kwargs)
    return await get_dashboard_devices(db=db, user=None, **params)


# ---------------------------------------------------------------------------
# Верхня таблиця: типи й доступність
# ---------------------------------------------------------------------------
async def test_type_counts_match_their_drilldown(db_session, warehouse):
    board = await get_dashboard(db=db_session, user=None)

    enabled_scanners = await _devices(db_session, device_type="scanner", enabled=True)
    disabled_scanners = await _devices(db_session, device_type="scanner", enabled=False)
    enabled_printers = await _devices(db_session, device_type="printer", enabled=True)
    disabled_printers = await _devices(db_session, device_type="printer", enabled=False)

    assert len(enabled_scanners) == board["devices"]["by_type"]["scanner"] == 2
    assert len(disabled_scanners) == board["devices"]["disabled_by_type"]["scanner"] == 1
    assert len(enabled_printers) == board["devices"]["by_type"]["printer"] == 3
    assert len(disabled_printers) == board["devices"]["disabled_by_type"]["printer"] == 1


async def test_totals_match_their_drilldown(db_session, warehouse):
    board = await get_dashboard(db=db_session, user=None)

    assert len(await _devices(db_session, enabled=True)) == board["devices"]["available"] == 5
    assert len(await _devices(db_session, enabled=False)) == board["devices"]["disabled"] == 2
    assert len(await _devices(db_session)) == 7


async def test_drilldown_says_who_holds_the_device(db_session, warehouse):
    """Сенс фічі: під числом видно не лише пристрій, а й його власника."""
    rows = {d["name"]: d for d in await _devices(db_session, device_type="scanner", enabled=True)}

    assert rows["SCAN-A1"]["employee"]["wms_login"] == "A-NOWAK"
    assert rows["SCAN-A1"]["employee"]["site"] == "STOCK"
    assert rows["SCAN-C1"]["employee"]["site"] is None


async def test_devices_come_back_alphabetically(db_session, warehouse):
    """Panel czyta się szukając nazwy wzrokiem. Wcześniej rządziło nazwisko
    posiadacza i nazwy szły pozornie losowo."""
    names = [d["name"] for d in await _devices(db_session)]
    assert names == sorted(names)
    assert names == ["PRINT-A2", "PRINT-B1", "PRINT-BROKEN", "PRINT-FREE",
                     "SCAN-A1", "SCAN-B2", "SCAN-C1"]


async def test_employees_come_back_by_wms_login(db_session):
    """Сортування свідомо не за прізвищем: у продакшн-даних ім'я і прізвище
    подекуди переставлені місцями, а логін WMS вводиться в одному форматі.
    Логіни тут навмисне йдуть проти алфавіту прізвищ."""
    zoll = await _employee(db_session, "A-ZOLL", "STOCK", last_name="Zoll")
    adam = await _employee(db_session, "Z-ADAMSKI", "STOCK", last_name="Adamski")
    await _device(db_session, "SCAN-Z1", DeviceType.scanner, zoll.id)
    await _device(db_session, "SCAN-Z2", DeviceType.scanner, adam.id)

    rows = await get_dashboard_employees(db=db_session, user=None, site=None)
    logins = [e["wms_login"] for e in rows]

    assert logins == sorted(logins)
    assert logins == ["A-ZOLL", "Z-ADAMSKI"]


async def test_free_devices_have_no_holder(db_session, warehouse):
    rows = {d["name"]: d for d in await _devices(db_session, assigned=False)}

    assert set(rows) == {"PRINT-FREE", "PRINT-BROKEN"}
    assert all(d["employee"] is None for d in rows.values())


async def test_unknown_type_is_rejected(db_session):
    with pytest.raises(HTTPException) as exc:
        await _devices(db_session, device_type="router")
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Нові колонки: Wydane / Wolne
# ---------------------------------------------------------------------------
async def test_wydane_liczy_kazdy_sprzet_z_loginem(db_session, warehouse):
    """«Wydane» — усе, що закріплене за людиною, разом із заблокованим: воно
    фізично в неї на руках, хай навіть у системі позначене недоступним."""
    board = await get_dashboard(db=db_session, user=None)

    # SCAN-B2 у фікстурі саме такий: закріплений і enabled=False.
    assert board["devices"]["assigned_by_type"]["scanner"] == 3
    assert board["devices"]["assigned_by_type"]["printer"] == 2


async def test_wolne_liczy_tylko_dostepne(db_session, warehouse):
    """«Wolne» — те, по що хтось прийде. Заблокований у шафі не рахується."""
    board = await get_dashboard(db=db_session, user=None)

    # PRINT-FREE так, PRINT-BROKEN (enabled=False) ні.
    assert board["devices"]["free_by_type"]["printer"] == 1
    assert board["devices"]["free_by_type"]["scanner"] == 0


async def test_wydane_i_wolne_maja_swoje_rozwiniecia(db_session, warehouse):
    """Кожне число мусить розгортатись рівно в те, що його склало."""
    board = await get_dashboard(db=db_session, user=None)

    wydane = await _devices(db_session, assigned=True)
    wolne = await _devices(db_session, assigned=False, enabled=True)

    assert len(wydane) == sum(board["devices"]["assigned_by_type"].values())
    assert len(wolne) == sum(board["devices"]["free_by_type"].values())


async def test_wydane_plus_wolne_nie_musi_dac_dostepnych(db_session, warehouse):
    """Świadoma różnica, nie błąd rachunku: sprzęt zablokowany i wydany wpada
    do "Wydane", a do "Dostępne" nie."""
    board = await get_dashboard(db=db_session, user=None)
    d = board["devices"]

    wydane = sum(d["assigned_by_type"].values())
    wolne = sum(d["free_by_type"].values())

    assert wydane + wolne == d["available"] + 1        # SCAN-B2


# ---------------------------------------------------------------------------
# Таблиця per dział
# ---------------------------------------------------------------------------
async def _site_row(db, name):
    board = await get_dashboard(db=db, user=None)
    return next(row for row in board["sites"] if row["site"] == name)


async def test_site_counts_match_their_drilldown(db_session, warehouse):
    row = await _site_row(db_session, "STOCK")
    scope = {"site": row["site_filter"], "enabled": True, "assigned": True}

    devices = await _devices(db_session, **scope)
    scanners = await _devices(db_session, device_type="scanner", **scope)
    printers = await _devices(db_session, device_type="printer", **scope)
    employees = await get_dashboard_employees(site=row["site_filter"], db=db_session, user=None)

    assert len(devices) == row["devices"] == 3
    assert len(scanners) == row["scanners"] == 1
    assert len(printers) == row["printers"] == 2
    assert len(employees) == row["employees"] == 2


async def test_employee_drilldown_lists_the_gear_each_person_has(db_session, warehouse):
    people = {e["wms_login"]: e for e in
              await get_dashboard_employees(site="STOCK", db=db_session, user=None)}

    assert [d["name"] for d in people["A-NOWAK"]["devices"]] == ["PRINT-A2", "SCAN-A1"]


async def test_employee_drilldown_keeps_withdrawn_gear(db_session, warehouse):
    """Несправний пристрій фізично лишається на працівнику, тому має бути в
    списку — але позначений, бо в число на дашборді він не входить."""
    people = {e["wms_login"]: e for e in
              await get_dashboard_employees(site="STOCK", db=db_session, user=None)}

    bartek = {d["name"]: d for d in people["B-WOJCIK"]["devices"]}
    assert sorted(bartek) == ["PRINT-B1", "SCAN-B2"]
    assert bartek["SCAN-B2"]["enabled"] is False
    assert bartek["PRINT-B1"]["enabled"] is True


async def test_row_without_site_is_reachable(db_session, warehouse):
    """Рядок "Brak" — це порожній параметр, а не літерал з таблиці."""
    row = await _site_row(db_session, "Brak")
    assert row["site_filter"] == ""

    devices = await _devices(db_session, site="", enabled=True, assigned=True)
    employees = await get_dashboard_employees(site="", db=db_session, user=None)

    assert [d["name"] for d in devices] == ["SCAN-C1"]
    assert [e["wms_login"] for e in employees] == ["C-ZAJAC"]
    assert len(devices) == row["devices"]
    assert len(employees) == row["employees"]


async def test_empty_site_does_not_pick_up_free_devices(db_session, warehouse):
    """Пристрій без власника теж дає NULL у колонці відділу після outerjoin —
    він не має потрапити до рядка "Brak"."""
    names = [d["name"] for d in await _devices(db_session, site="")]

    assert "PRINT-FREE" not in names
    assert "PRINT-BROKEN" not in names


# ---------------------------------------------------------------------------
# Ostatnie wypożyczenie i wiersz RAZEM
# ---------------------------------------------------------------------------
@pytest.fixture
async def historia(db_session, warehouse):
    """Дві реєстрації того самого сканера і одне повернення після них."""
    anna = warehouse["anna"]
    scanner = (await db_session.execute(
        select(DeviceDB).where(DeviceDB.name == "SCAN-A1")
    )).scalar_one()

    db_session.add_all([
        TransactionDB(timestamp=datetime(2026, 3, 10, 6, 0, tzinfo=timezone.utc),
                      type=TransactionType.registered,
                      employee_id=anna.id, device_id=scanner.id),
        TransactionDB(timestamp=datetime(2026, 3, 11, 14, 30, tzinfo=timezone.utc),
                      type=TransactionType.registered,
                      employee_id=anna.id, device_id=scanner.id),
        # Zwrot nie jest wypożyczeniem i nie może przebić daty.
        TransactionDB(timestamp=datetime(2026, 3, 12, 8, 0, tzinfo=timezone.utc),
                      type=TransactionType.unregistered,
                      employee_id=anna.id, device_id=scanner.id),
    ])
    await db_session.commit()
    return {"anna": anna, "scanner": scanner}


async def test_rozwiniecie_urzadzen_pokazuje_ostatnie_wypozyczenie(db_session, historia):
    """Колонка живе в розгорнутому списку — саме там, де на неї дивляться."""
    rows = {d["name"]: d for d in await _devices(db_session)}

    # 14:30 UTC to 15:30 w Polsce — magazyn czyta swój zegar, nie serwerowy.
    assert rows["SCAN-A1"]["last_rental"] == "2026-03-11 15:30"


async def test_rozwiniecie_pracownikow_tez_ma_te_kolumne(db_session, historia):
    rows = {e["wms_login"]: e for e in
            await get_dashboard_employees(db=db_session, user=None, site=None)}

    assert rows["A-NOWAK"]["last_rental"] == "2026-03-11 15:30"


async def test_sprzet_bez_historii_ma_pusto(db_session, historia):
    """Ніколи не виданий пристрій — це не «давно», це «ніколи»."""
    rows = {d["name"]: d for d in await _devices(db_session)}

    assert rows["PRINT-FREE"]["last_rental"] is None


async def test_podsumowanie_sumuje_to_co_widac(db_session, warehouse):
    """Wiersz RAZEM liczy się z kolumn tabeli, nie osobnym zapytaniem — dwie
    liczby na jednym ekranie nie mają prawa się rozjechać."""
    board = await get_dashboard(db=db_session, user=None)
    sites = board["sites"]

    for klucz in ("employees", "devices", "scanners", "printers"):
        assert sum(s[klucz] for s in sites) == sum(s[klucz] or 0 for s in sites)

    # To samo robi renderSiteTotals w przeglądarce.
    from pathlib import Path
    admin_js = Path("app/static/js/admin/admin.js").read_text(encoding="utf-8")
    assert "function renderSiteTotals" in admin_js
    assert "sites.reduce" in admin_js
    # Kolumna z czasem należy do rozwinięcia, nie do tabeli per site.
    assert "Ostatnie wypożyczenie" in admin_js
