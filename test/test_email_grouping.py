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
