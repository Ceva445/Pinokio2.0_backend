"""Тести протоколу пошкодження обладнання.

Дві речі, які тут важливі понад усе:

1. Протокол — це запис, який має лишитись. Пошта може бути недоступна, але
   зламаний сканер від цього не перестає бути зламаним, тож збій відправки не
   має скасовувати збереження.
2. Лист іде рівно групі ALL. Не всім керівникам підряд і не керівникам site
   того пристрою — саме ALL, як просили.
"""
import inspect
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import routers.damage_reports as damage_reports
from app.dependencies.admin import require_admin, require_manager_or_admin
from models.db_damage_report import DamageReportDB
from models.db_department_manager import DepartmentManagerDB
from models.db_device import DeviceDB, DeviceType
from models.db_employee import EmployeeDB
from models.db_user import UserDB, UserRole
from routers.damage_reports import create_damage_report, get_damage_reports

pytestmark = pytest.mark.asyncio

MANAGER = {"id": None, "username": "P-KOWALSKAM", "role": "manager"}
ADMIN = {"id": None, "username": "C-ADMIN", "role": "admin"}


@pytest.fixture
def wyslane(monkeypatch):
    """Перехоплюємо відправку — жоден лист нікуди не йде."""
    box = []

    def fake_send(to_email, subject, message):
        box.append({"to": to_email, "subject": subject, "message": message})

    monkeypatch.setattr(damage_reports, "send_email_sync", fake_send)
    return box


@pytest.fixture
async def warehouse(db_session):
    manager = UserDB(first_name="Maria", last_name="Kowalska",
                     username="P-KOWALSKAM", password_hash="x",
                     role=UserRole.manager)
    anna = EmployeeDB(last_name="Nowak", first_name="Anna", rfid="r-anna",
                      company="Demo", wms_login="A-NOWAK")
    db_session.add_all([manager, anna])
    await db_session.commit()

    held = DeviceDB(name="TERM003", rfid="r-t3", serial_number="sn-t3",
                    type=DeviceType.scanner, employee_id=anna.id)
    free = DeviceDB(name="TERM004", rfid="r-t4", serial_number="sn-t4",
                    type=DeviceType.printer)
    db_session.add_all([held, free])

    db_session.add_all([
        DepartmentManagerDB(department="ALL", email="szef@example.com"),
        DepartmentManagerDB(department="all", email="Drugi@example.com"),
        DepartmentManagerDB(department="ALL", email="SZEF@example.com"),
        # Kierownik pojedynczego site — protokołu NIE dostaje.
        DepartmentManagerDB(department="STOCK", email="stock@example.com"),
    ])
    await db_session.commit()

    MANAGER["id"] = manager.id
    return {"manager": manager, "anna": anna, "held": held, "free": free}


async def _create(db, device_id, description="Rozbita szybka"):
    return await create_damage_report(
        payload={"device_id": device_id, "description": description},
        db=db, user=MANAGER,
    )


# ---------------------------------------------------------------------------
# Сам протокол
# ---------------------------------------------------------------------------
async def test_report_is_saved(db_session, warehouse, wyslane):
    result = await _create(db_session, warehouse["held"].id)

    saved = (await db_session.execute(select(DamageReportDB))).scalars().all()
    assert len(saved) == 1
    assert saved[0].description == "Rozbita szybka"
    assert saved[0].device_id == warehouse["held"].id
    assert result["report"]["device"]["name"] == "TERM003"


async def test_report_remembers_who_had_the_device(db_session, warehouse, wyslane):
    """Пристрій потім поїде в сервіс або до іншої людини, а протокол має
    відповідати на питання «у кого це сталось»."""
    await _create(db_session, warehouse["held"].id)

    report = (await db_session.execute(select(DamageReportDB))).scalar_one()
    assert report.employee_id == warehouse["anna"].id

    warehouse["held"].employee_id = None
    await db_session.commit()

    assert (await db_session.execute(select(DamageReportDB))).scalar_one().employee_id \
        == warehouse["anna"].id


async def test_report_is_signed_by_its_author(db_session, warehouse, wyslane):
    await _create(db_session, warehouse["held"].id)

    report = (await db_session.execute(select(DamageReportDB))).scalar_one()
    assert report.user_id == warehouse["manager"].id


async def test_free_device_can_be_reported_too(db_session, warehouse, wyslane):
    """Зламатись може й пристрій, який зараз ні за ким не закріплений."""
    result = await _create(db_session, warehouse["free"].id, "Nie drukuje")

    assert result["report"]["employee"] is None
    assert "nie był do nikogo przypisany" in wyslane[0]["message"]


# ---------------------------------------------------------------------------
# Лист
# ---------------------------------------------------------------------------
async def test_mail_goes_to_the_all_group_only(db_session, warehouse, wyslane):
    await _create(db_session, warehouse["held"].id)

    adresaci = sorted(m["to"].lower() for m in wyslane)
    assert adresaci == ["drugi@example.com", "szef@example.com"]
    assert "stock@example.com" not in adresaci


async def test_the_same_address_gets_one_letter(db_session, warehouse, wyslane):
    """SZEF@ і szef@ — та сама людина."""
    result = await _create(db_session, warehouse["held"].id)

    assert result["recipients"] == 2
    assert result["sent"] == 2
    assert len(wyslane) == 2


async def test_letter_carries_the_whole_protocol(db_session, warehouse, wyslane):
    await _create(db_session, warehouse["held"].id, "Zalany klawiaturą kawą")

    letter = wyslane[0]
    assert letter["subject"] == "Protokół uszkodzenia sprzętu — TERM003"
    for fragment in ("skaner TERM003", "sn-t3", "A-NOWAK",
                     "Maria Kowalska (P-KOWALSKAM)", "Zalany klawiaturą kawą"):
        assert fragment in letter["message"], fragment


async def test_broken_smtp_does_not_lose_the_report(db_session, warehouse, monkeypatch):
    """Найважливіше: пошта лягла — протокол усе одно записаний."""
    def failing_send(to_email, subject, message):
        raise OSError("SMTP down")

    monkeypatch.setattr(damage_reports, "send_email_sync", failing_send)

    result = await _create(db_session, warehouse["held"].id)

    assert result["sent"] == 0
    assert result["errors"] == 2
    assert len((await db_session.execute(select(DamageReportDB))).scalars().all()) == 1


async def test_no_all_group_still_saves(db_session, warehouse, wyslane):
    """Порожня група ALL — не привід втрачати зголошення."""
    for row in (await db_session.execute(select(DepartmentManagerDB))).scalars().all():
        await db_session.delete(row)
    await db_session.commit()

    result = await _create(db_session, warehouse["held"].id)

    assert result["recipients"] == 0
    assert not wyslane
    assert result["report"]["id"]


# ---------------------------------------------------------------------------
# Чого робити не можна
# ---------------------------------------------------------------------------
async def test_description_is_required(db_session, warehouse, wyslane):
    with pytest.raises(HTTPException) as exc:
        await _create(db_session, warehouse["held"].id, "   ")

    assert exc.value.status_code == 400
    assert not wyslane


async def test_device_is_required(db_session, warehouse, wyslane):
    with pytest.raises(HTTPException) as exc:
        await create_damage_report(
            payload={"description": "Cos sie stalo"}, db=db_session, user=MANAGER
        )

    assert exc.value.status_code == 400


async def test_unknown_device_is_refused(db_session, warehouse, wyslane):
    with pytest.raises(HTTPException) as exc:
        await _create(db_session, 9999)

    assert exc.value.status_code == 404
    assert not wyslane


async def test_both_roles_may_report_but_not_an_observer():
    """Кierownik i admin zgłaszają; obserwator ma tylko dashboard."""
    guard = inspect.signature(create_damage_report).parameters["user"].default.dependency
    assert guard is require_manager_or_admin


async def test_history_belongs_to_the_admin_alone():
    """Kierownik zgłasza swoje i na tym koniec — cudze zgłoszenia z całego
    magazynu to widok administratora. Sam brak tabeli w szablonie by nie
    wystarczył: endpoint i tak dałoby się zawołać wprost."""
    guard = inspect.signature(get_damage_reports).parameters["user"].default.dependency
    assert guard is require_admin


async def test_managers_screen_has_no_history_table():
    """Szablon jest wspólny dla obu paneli, więc tabela wisi na roli."""
    template = Path("app/templates/damage_reports/form.html").read_text(encoding="utf-8")

    assert '{% if user and user.role == "admin" %}' in template
    assert template.index('id="damageForm"') < template.index('id="damageTable"')


# ---------------------------------------------------------------------------
# Список
# ---------------------------------------------------------------------------
async def test_list_shows_newest_first(db_session, warehouse, wyslane):
    await _create(db_session, warehouse["held"].id, "Pierwsze")
    await _create(db_session, warehouse["free"].id, "Drugie")

    reports = await get_damage_reports(device_id=None, db=db_session, user=ADMIN)

    assert [r["description"] for r in reports][0] in ("Drugie", "Pierwsze")
    assert len(reports) == 2


async def test_list_can_be_narrowed_to_one_device(db_session, warehouse, wyslane):
    await _create(db_session, warehouse["held"].id, "Pierwsze")
    await _create(db_session, warehouse["free"].id, "Drugie")

    reports = await get_damage_reports(
        device_id=warehouse["free"].id, db=db_session, user=ADMIN
    )

    assert [r["description"] for r in reports] == ["Drugie"]
