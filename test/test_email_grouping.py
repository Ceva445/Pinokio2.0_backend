"""Тести групування в розсилці «не повернув пристрій».

Раніше ключем був вільний текст `employees.department`, а керівник шукався
точним збігом рядка. Досить було `Stock` замість `STOCK` — і жоден керівник
не знаходився, лист не йшов, і ніхто цього не помічав.

Тепер ключ — назва site зі словника, тож розійтися нема чому.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.db_device import DeviceDB, DeviceType
from models.db_employee import EmployeeDB
from models.db_site import SiteDB

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def warehouse(db_session):
    stock = SiteDB(name="STOCK")
    emag = SiteDB(name="EMAG")
    db_session.add_all([stock, emag])
    await db_session.commit()

    people = [
        EmployeeDB(last_name="Nowak", first_name="Anna", rfid="r-a",
                   company="ACME", wms_login="A-NOWAK", site_id=stock.id),
        EmployeeDB(last_name="Wojcik", first_name="Bartek", rfid="r-b",
                   company="ACME", wms_login="B-WOJCIK", site_id=stock.id),
        EmployeeDB(last_name="Zajac", first_name="Cezary", rfid="r-c",
                   company="ACME", wms_login="C-ZAJAC", site_id=emag.id),
        # Bez site — kiedyś takich nie było, bo każdy miał wpisany tekst.
        EmployeeDB(last_name="Dab", first_name="Dorota", rfid="r-d",
                   company="ACME", wms_login="D-DAB", site_id=None),
    ]
    db_session.add_all(people)
    await db_session.commit()

    return {"stock": stock, "emag": emag, "people": people}


async def _grouping(db) -> dict:
    """Ключ групування такий самий, як його рахує email_agent."""
    rows = (await db.execute(
        select(EmployeeDB).options(selectinload(EmployeeDB.site))
    )).scalars().all()

    grouped: dict = {}
    for employee in rows:
        key = employee.site.name if employee.site else None
        grouped.setdefault(key, []).append(employee.wms_login)
    return grouped


async def test_people_group_by_site_name(db_session, warehouse):
    grouped = await _grouping(db_session)

    assert sorted(grouped["STOCK"]) == ["A-NOWAK", "B-WOJCIK"]
    assert grouped["EMAG"] == ["C-ZAJAC"]


async def test_letter_case_cannot_split_a_site_anymore(db_session, warehouse):
    """Сенс усієї заміни: назва береться зі словника, а не з поля вводу.

    Раніше «Stock» і «STOCK» давали два ключі, і люди з першого не потрапляли
    до жодного керівника."""
    grouped = await _grouping(db_session)

    assert [key for key in grouped if key and key.upper() == "STOCK"] == ["STOCK"]


async def test_person_without_site_lands_in_its_own_bucket(db_session, warehouse):
    """Такий працівник не має керівника — але й не псує чужу групу."""
    grouped = await _grouping(db_session)

    assert grouped[None] == ["D-DAB"]


async def test_renaming_a_site_moves_everyone_at_once(db_session, warehouse):
    """FK замість тексту: перейменування майданчика не лишає нікого позаду."""
    warehouse["stock"].name = "STOCK PL"
    await db_session.commit()

    grouped = await _grouping(db_session)

    assert sorted(grouped["STOCK PL"]) == ["A-NOWAK", "B-WOJCIK"]
    assert "STOCK" not in grouped


async def test_mail_agent_reads_the_site_not_the_text(db_session, warehouse):
    """Сам запит агента: у вибірці має бути назва site."""
    import inspect

    from routers import email_agent

    source = inspect.getsource(email_agent)

    assert 'SiteDB.name.label("site")' in source
    assert "EmployeeDB.department" not in source
    assert "DepartmentManagerDB.department == site" in source


async def test_device_still_hangs_on_its_holder(db_session, warehouse):
    """Дрібна перевірка звʼязку, на якому тримається вся вибірка агента."""
    anna = warehouse["people"][0]
    device = DeviceDB(name="TERM003", rfid="r-t3", serial_number="sn-t3",
                      type=DeviceType.scanner, employee_id=anna.id)
    db_session.add(device)
    await db_session.commit()

    held = (await db_session.execute(
        select(DeviceDB).where(DeviceDB.employee_id == anna.id)
    )).scalars().all()

    assert [d.name for d in held] == ["TERM003"]

# ---------------------------------------------------------------------------
# Kolejność i pogrubienie
# ---------------------------------------------------------------------------
@pytest.fixture
def przechwycone(monkeypatch):
    """Перехоплюємо відправку — жоден лист нікуди не йде."""
    skrzynka = []

    def fake_send(to_email, subject, message, html=None):
        skrzynka.append({"to": to_email, "subject": subject,
                         "message": message, "html": html})

    import routers.email_agent as ea
    monkeypatch.setattr(ea, "send_email_sync", fake_send)
    return skrzynka


@pytest.fixture
async def zalegle(db_session, warehouse):
    """Trzy osoby z jednego site i jedna z drugiego, każda trzyma sprzęt od
    innego czasu — dość, żeby sprawdzić kolejność."""
    from datetime import datetime, timedelta, timezone

    from models.db_department_manager import DepartmentManagerDB
    from models.db_transaction import TransactionDB, TransactionType

    def temu(godzin):
        return datetime.now(tz=timezone.utc) - timedelta(hours=godzin)

    osoby = warehouse["people"]
    urzadzenia = []
    for i, (osoba, godzin) in enumerate(
        [(osoby[0], 3), (osoby[1], 30), (osoby[2], 9)], start=1
    ):
        d = DeviceDB(name=f"TERM00{i}", rfid=f"rr{i}", serial_number=f"ss{i}",
                     type=DeviceType.scanner, employee_id=osoba.id)
        db_session.add(d)
        await db_session.commit()
        urzadzenia.append((d, osoba, godzin))

    db_session.add_all([
        TransactionDB(timestamp=temu(godzin), type=TransactionType.registered,
                      employee_id=osoba.id, device_id=d.id)
        for d, osoba, godzin in urzadzenia
    ])
    db_session.add(DepartmentManagerDB(department="ALL", email="szef@example.com"))
    await db_session.commit()
    return warehouse


async def _zbiorczy(db, skrzynka):
    from routers.email_agent import run_email_notifications

    await run_email_notifications(db)
    return next(m for m in skrzynka if "wszystkie" in m["subject"])


def _sekcje(tresc: str) -> dict[str, list[int]]:
    """Godziny z każdej sekcji osobno — list jest pogrupowany po site, więc
    kolejność sprawdza się wewnątrz grupy, nie przez całą treść."""
    sekcje, biezaca = {}, None
    for wiersz in tresc.splitlines():
        if wiersz.startswith("["):
            biezaca = wiersz.strip("[]")
            sekcje[biezaca] = []
        elif biezaca and "—" in wiersz and "(skaner" in wiersz:
            sekcje[biezaca].append(int(wiersz.split("—")[1].split("h")[0]))
    return sekcje


async def test_najdluzej_trzymane_na_gorze(db_session, zalegle, przechwycone):
    """Сенс листа — побачити найгірші випадки першими."""
    list_ = await _zbiorczy(db_session, przechwycone)
    sekcje = _sekcje(list_["message"])

    assert sekcje["STOCK"] == [30, 3]
    for godziny in sekcje.values():
        assert godziny == sorted(godziny, reverse=True)


async def test_dzialy_ida_od_najgorszego(db_session, zalegle, przechwycone):
    """Pierwszy ten site, który ma najdłużej niezwrócony sprzęt."""
    list_ = await _zbiorczy(db_session, przechwycone)
    kolejnosc = [w.strip("[]") for w in list_["message"].splitlines() if w.startswith("[")]

    # STOCK ma osobę z 30h, EMAG z 9h.
    assert kolejnosc == ["STOCK", "EMAG"]


async def test_okres_jest_pogrubiony_w_html(db_session, zalegle, przechwycone):
    list_ = await _zbiorczy(db_session, przechwycone)

    assert "<b>" in list_["html"]
    assert "godzin</b>:" in list_["html"] or "(stan na teraz)</b>:" in list_["html"]


async def test_czysty_tekst_zostaje_bez_znacznikow(db_session, zalegle, przechwycone):
    """Druga część listu to nadal czysty tekst — dla klientów bez HTML."""
    list_ = await _zbiorczy(db_session, przechwycone)

    assert "<b>" not in list_["message"]
    assert "<li>" not in list_["message"]


async def test_oba_listy_maja_te_same_wiersze(db_session, zalegle, przechwycone):
    """HTML i tekst nie mogą się rozjechać — to ten sam list."""
    list_ = await _zbiorczy(db_session, przechwycone)
    wiersze = [w for w in list_["message"].splitlines()
               if "—" in w and "(skaner" in w]

    for w in wiersze:
        assert w in list_["html"].replace("&nbsp;", " ")


async def test_nazwiska_ida_przez_escape(db_session, warehouse, przechwycone):
    """Imię wpisuje człowiek, a w HTML ma zostać tekstem, nie znacznikiem."""
    from datetime import datetime, timedelta, timezone

    from models.db_department_manager import DepartmentManagerDB
    from models.db_transaction import TransactionDB, TransactionType

    osoba = warehouse["people"][0]
    osoba.last_name = "O<b>Brien</b>"
    d = DeviceDB(name="TERM999", rfid="r9", serial_number="s9",
                 type=DeviceType.scanner, employee_id=osoba.id)
    db_session.add_all([d, DepartmentManagerDB(department="ALL", email="szef@example.com")])
    await db_session.commit()
    db_session.add(TransactionDB(
        timestamp=datetime.now(tz=timezone.utc) - timedelta(hours=20),
        type=TransactionType.registered, employee_id=osoba.id, device_id=d.id))
    await db_session.commit()

    list_ = await _zbiorczy(db_session, przechwycone)

    assert "O&lt;b&gt;Brien" in list_["html"]


async def test_prog_w_napisie_bierze_sie_z_konfiguracji():
    """Napis nie może mówić "12 godzin", gdy admin ustawił inną liczbę."""
    import inspect

    from routers import email_agent

    zrodlo = inspect.getsource(email_agent.run_email_notifications)

    assert "progowe_godziny = hours" in zrodlo
    assert "przez ponad 12 godzin" not in zrodlo


async def test_list_idzie_jako_multipart_gdy_jest_html(monkeypatch):
    """multipart/alternative: klient z HTML widzi pogrubienie, bez HTML —
    czysty tekst. Bez tej pary pogrubienia nie ma gdzie umieścić."""
    import routers.email_agent as ea

    wyslane = {}

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, *a): pass
        def sendmail(self, nadawca, odbiorcy, tresc): wyslane["raw"] = tresc

    monkeypatch.setattr(ea.smtplib, "SMTP", FakeSMTP)

    ea.send_email_sync("a@example.com", "temat", "czysty", "<p><b>html</b></p>")
    assert "multipart/alternative" in wyslane["raw"]
    assert "text/plain" in wyslane["raw"] and "text/html" in wyslane["raw"]

    ea.send_email_sync("a@example.com", "temat", "czysty")
    assert "multipart" not in wyslane["raw"]
