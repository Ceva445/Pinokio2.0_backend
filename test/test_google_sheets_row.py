"""Тести рядка, який синхронізація пише в Google Sheet.

Оновлення перезаписує ВЕСЬ рядок, тож кожна колонка мусить мати значення.
MODEL і три колонки портів діставали порожній рядок, і кожен запис їх стирав.

Порти з бази тепер ідуть у PORT EMAG, один під одним: у `device_ports` лежить
самий номер, без позначки, до якої з трьох колонок він належить. Для решти
колонок, яких застосунок не веде, єдине правильне значення — те, що вже
стоїть в аркуші.
"""
from datetime import date

import pytest

from services.google_sheets import generate_line_to_write

# Заголовки взяті з живого аркуша (рядок 3 на обох вкладках).
SCANNER_COLUMNS = [
    "S/N", "PORT EMAG", "PORT 445", "PORT 999", "SITE",
    "MODEL", "Nazwa", "STATUS", "Notatka", "Inventaryzoano",
]
PRINTER_COLUMNS = [
    "Nazwa", "S/N", "IP", "MODEL", "SITE", "STATUS", "Notatka", "Inventaryzoano",
]

# TERM001 так, як він виглядає в аркуші сьогодні.
SCANNER_ROW = [
    "s24339524215996", "8226", "20101", "", "EMAG",
    "MC930B", "TERM001", "WORK", "stara notatka", "2024-05-23",
]


class _Named:
    def __init__(self, name):
        self.name = name


class _Port:
    def __init__(self, port_number):
        self.port_number = port_number


class _Device:
    def __init__(self, **kwargs):
        self.serial_number = kwargs.get("serial_number", "s24339524215996")
        self.rfid = kwargs.get("rfid", "04:24:68:1D")
        self.name = kwargs.get("name", "TERM001")
        self.ip = kwargs.get("ip")
        self.status = kwargs.get("status")
        self.site = kwargs.get("site")
        self.ports = kwargs.get("ports", [])


def _row(device, columns=SCANNER_COLUMNS, previous=None, notes="nowa notatka"):
    return generate_line_to_write(
        device=device,
        line_of_position_column=columns,
        notes=notes,
        previous_row=list(SCANNER_ROW if previous is None else previous),
    )


# ---------------------------------------------------------------------------
# Те, через що завдання й виникло
# ---------------------------------------------------------------------------
def test_ports_from_the_database_go_into_the_emag_column():
    """Порти в базі лежать без позначки колонки, тож усі йдуть в PORT EMAG —
    один під одним в одній комірці."""
    device = _Device(site=_Named("EMAG"), status=_Named("WORK"),
                     ports=[_Port("20103"), _Port("8226")])

    assert _row(device)[1] == "8226\n20103"


def test_ports_keep_a_stable_order():
    """Порядок не має стрибати від запису до запису: 8226 перед 20103,
    а не «двадцять» перед «вісім» за алфавітом."""
    ascending = _row(_Device(ports=[_Port("8226"), _Port("20103")]))[1]
    descending = _row(_Device(ports=[_Port("20103"), _Port("8226")]))[1]

    assert ascending == descending == "8226\n20103"


def test_missing_ports_do_not_erase_the_column():
    """TERM001 має в аркуші 8226, а в базі жодного порту — порожній запис
    зʼїв би те, що склад вписав руками."""
    device = _Device(site=_Named("EMAG"), status=_Named("WORK"), ports=[])

    assert _row(device)[1] == "8226"


def test_the_other_two_port_columns_are_left_alone():
    """Що означають PORT 445 і PORT 999, застосунок не знає — не чіпає."""
    row = _row(_Device(ports=[_Port("20103")]))

    assert row[2] == "20101"
    assert row[3] == ""


def test_model_survives_a_sync():
    device = _Device(site=_Named("EMAG"), status=_Named("WORK"))

    assert _row(device)[5] == "MC930B"


def test_printer_model_survives_too():
    """Друкарки мають власну вкладку з іншим порядком колонок."""
    previous = ["ZEBRAMOB44501", "xxrbn245103077", "10.6.251.4", "ZQ630",
                "EMAG", "WORK", "stara notatka", "2026-09-10"]
    device = _Device(name="ZEBRAMOB44501", serial_number="xxrbn245103077",
                     ip="10.6.251.4", site=_Named("EMAG"), status=_Named("WORK"))

    row = _row(device, columns=PRINTER_COLUMNS, previous=previous)

    assert row[3] == "ZQ630"


def test_unknown_column_is_left_alone():
    """Магазин дописує колонки збоку — вони теж не мають зникати."""
    columns = SCANNER_COLUMNS + ["Uwagi magazynu"]
    previous = SCANNER_ROW + ["oddane do serwisu"]
    device = _Device(site=_Named("EMAG"), status=_Named("WORK"))

    assert _row(device, columns=columns, previous=previous)[10] == "oddane do serwisu"


def test_short_previous_row_does_not_explode():
    """Аркуш обрізає хвостові порожні клітинки, тож рядок буває коротшим."""
    device = _Device(site=_Named("EMAG"), status=_Named("WORK"))

    row = _row(device, previous=["s24339524215996", "8226"])

    assert row[5] == ""
    assert len(row) == len(SCANNER_COLUMNS)


# ---------------------------------------------------------------------------
# Те, що застосунок веде сам — має й далі перезаписуватись
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("index, expected", [
    (0, "s24339524215996"),
    (4, "STOCK"),
    (6, "TERM001"),
    (7, "SERWIS"),
    (8, "nowa notatka"),
])
def test_own_columns_are_overwritten(index, expected):
    device = _Device(site=_Named("STOCK"), status=_Named("SERWIS"))

    assert _row(device)[index] == expected


def test_inventory_date_is_today():
    device = _Device(site=_Named("EMAG"), status=_Named("WORK"))

    assert _row(device)[9] == str(date.today())


def test_empty_database_values_never_clear_the_sheet():
    """Статуси й IP потрапили в застосунок пізніше, ніж в аркуш, тож для
    частини сприяту база їх просто не знає. Порожній запис зʼїдав складу дані,
    яких немає звідки відновити."""
    row = _row(_Device(status=None, site=None))

    assert row[4] == "EMAG"
    assert row[7] == "WORK"


def test_printer_without_ip_keeps_the_one_from_the_sheet():
    previous = ["ZEBRAMOB44504", "XXRBN245103099", "10.6.251.4", "ZQ630",
                "EMAG", "WORK", "stara notatka", "2026-09-10"]
    device = _Device(name="ZEBRAMOB44504", serial_number="XXRBN245103099",
                     ip=None, status=None, site=None)

    row = _row(device, columns=PRINTER_COLUMNS, previous=previous)

    assert row[2] == "10.6.251.4"
    assert row[5] == "WORK"
