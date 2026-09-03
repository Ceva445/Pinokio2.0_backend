# services/device_transactions.py

import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from models.db_device import DeviceDB, DeviceType
from models.db_device_status import DeviceStatusDB
from models.db_site import SiteDB
from models.device_transaction import DeviceChangeTransaction

from services.google_sheets import sync_device_to_sheet


logger = logging.getLogger(__name__)


FIELD_LABELS = {
    "name": "device name",
    "serial_number": "device serial number",
    "rfid": "device rfid",
    "ip": "device ip",
    "type": "device type",
    "status_id": "device status",
    "enabled": "device enabled",
    "site_id": "device site",
    "ports": "device ports"
}


async def build_change_descriptions(
    db: AsyncSession,
    device: DeviceDB,
    changes: dict
) -> list[str]:

    descriptions = []

    for field, values in changes.items():

        old_value = values["old"]
        new_value = values["new"]

        if field == "status_id":

            old_status = None
            new_status = None

            if old_value:
                result = await db.execute(
                    select(DeviceStatusDB).where(
                        DeviceStatusDB.id == old_value
                    )
                )
                old_status_obj = result.scalar_one_or_none()
                old_status = old_status_obj.name if old_status_obj else None

            if new_value:
                result = await db.execute(
                    select(DeviceStatusDB).where(
                        DeviceStatusDB.id == new_value
                    )
                )
                new_status_obj = result.scalar_one_or_none()
                new_status = new_status_obj.name if new_status_obj else None

            descriptions.append(
                f"changed device status {old_status} to {new_status}"
            )

            continue

        if field == "site_id":

            old_site = await db.get(SiteDB, old_value) if old_value else None
            new_site = await db.get(SiteDB, new_value) if new_value else None

            descriptions.append(
                f"changed device site "
                f"{old_site.name if old_site else None} to "
                f"{new_site.name if new_site else None}"
            )

            continue

        if field == "type":

            old_value = old_value.value if old_value else None
            new_value = new_value.value if new_value else None

        label = FIELD_LABELS.get(field, field)

        descriptions.append(
            f"changed {label} {old_value} to {new_value}"
        )

    return descriptions


async def create_device_transaction(
    db: AsyncSession,
    user_id: int,
    device: DeviceDB,
    descriptions: list[str],
    note: str | None = None
):

    if not descriptions:
        return

    timestamp = datetime.now().strftime("%Y-%m-%d")

    notes = (
        f"{timestamp} User: admin "
        + " ".join(descriptions)
    )

    # Довільна нотатка адміна — додається в КІНЕЦЬ опису транзакції
    if note and note.strip():
        notes = notes + " | Notatka: " + note.strip()

    transaction = DeviceChangeTransaction(
        user_id=user_id,
        device_id=device.id,
        description=notes
    )

    db.add(transaction)

    await db.flush()

    # Дзеркалення в Google Sheet — best-effort: збій (напр. 429 rate limit,
    # мережа) НЕ повинен валити успішну зміну девайса у 500.
    try:
        await sync_device_to_sheet(
            db=db,
            device_id=device.id,
            notes=notes
        )
    except Exception as exc:
        logger.warning("sync_device_to_sheet failed (non-fatal): %s", exc)