# services/google_sheets.py

from datetime import date
import os

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.db_device import DeviceDB, DeviceType

from dotenv import load_dotenv
load_dotenv()

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

credentials = Credentials.from_service_account_file(
    "creds.json",
    scopes=SCOPES
)

service = build("sheets", "v4", credentials=credentials)


def get_sheet_name(device: DeviceDB) -> str:
    if device.type == DeviceType.scanner:
        return "SCANER"

    if device.type == DeviceType.printer:
        return "PRINTER"

    raise Exception(f"Unknown device type: {device.type}")


def generate_line_to_write(
    device: DeviceDB,
    line_of_position_column: list[str],
    notes: str
) -> list[str]:

    result_line = []

    for field in line_of_position_column:

        if field == "S/N":
            result_line.append(device.serial_number)

        elif field == "RFID":
            result_line.append(device.rfid)

        elif field == "Nazwa":
            result_line.append(device.name)

        elif field == "IP":
            result_line.append(device.ip or "")

        elif field == "STATUS":
            result_line.append(
                device.status.name if device.status else ""
            )

        elif field == "MODEL":
            result_line.append("")

        elif field == "SITE":
            result_line.append(device.site.value if device.site else "")

        elif field == "Inventaryzoano":
            result_line.append(str(date.today()))

        elif field == "Notatka":
            result_line.append(notes)

        elif field == "PORTS":

            port_name = field.replace("PORTS", "").strip()
            ports = [p for p in device.ports if port_name in p.port_number]
            result_line.append(
                "\n".join(str(p.port_number) for p in ports) if ports else ""
            )

        else:
            result_line.append("")

    return result_line


def write_dev_change_to_spreadsheet(
    row_to_write: list[str],
    row_index: int,
    previous_row: list[str],
    line_of_position_column: list[str],
    spread_sheet_name: str
):

    for list_index, column_name in enumerate(line_of_position_column):

        if column_name == "Notatka":

            previous_notes = ""

            if list_index < len(previous_row):
                previous_notes = previous_row[list_index]

            row_to_write[list_index] = (
                previous_notes + "\n" + row_to_write[list_index]
            )

    num_columns = len(row_to_write)

    end_column_letter = chr(64 + num_columns)

    update_range = (
        f"{spread_sheet_name}!A{row_index}:{end_column_letter}{row_index}"
    )

    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=update_range,
        valueInputOption="RAW",
        body={
            "values": [row_to_write]
        },
    ).execute()


async def sync_device_to_sheet(
    db,
    device_id: int,
    notes: str
):

    result = await db.execute(
        select(DeviceDB)
        .options(
            selectinload(DeviceDB.status),
            selectinload(DeviceDB.ports)
        )
        .where(DeviceDB.id == device_id)
    )

    device = result.scalar_one()

    spread_sheet_name = get_sheet_name(device)

    response = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=SPREADSHEET_ID,
            range=spread_sheet_name
        )
        .execute()
    )

    values = response.get("values", [])

    if not values:
        return

    line_of_position_column = values[2]

    device_coordinate = None
    previous_row = None

    for row_index, row_values in enumerate(values):

        if device.name in row_values:

            device_coordinate = row_index + 1
            previous_row = row_values

            break

    if not device_coordinate:
        return

    if len(previous_row) < len(line_of_position_column):

        previous_row.extend(
            [
                ""
                for _ in range(
                    len(line_of_position_column) - len(previous_row)
                )
            ]
        )

    row_to_write = generate_line_to_write(
        device=device,
        line_of_position_column=line_of_position_column,
        notes=notes
    )

    write_dev_change_to_spreadsheet(
        row_to_write=row_to_write,
        row_index=device_coordinate,
        previous_row=previous_row,
        line_of_position_column=line_of_position_column,
        spread_sheet_name=spread_sheet_name,
    )

def write_report_gs(
    data: list[list],
    sheet_name: str
):

    body = {
        "values": data
    }

    num_rows = len(data)
    num_cols = len(data[0])

    last_column = chr(ord("A") + num_cols - 1)
    last_row = num_rows

    range_ = f"{sheet_name}!A1:{last_column}{last_row}"

    service.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range=sheet_name,
    ).execute()

    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=range_,
        valueInputOption="RAW",
        includeValuesInResponse=True,
        body=body,
    ).execute()


def read_all_sheets(
    SPREADSHEET_ID_param: str | None = None
):

    target_SPREADSHEET_ID = (
        SPREADSHEET_ID_param or SPREADSHEET_ID
    )

    sheets = (
        service.spreadsheets()
        .get(
            spreadsheetId=target_SPREADSHEET_ID
        )
        .execute()
    )

    not_dev_st_list = [
        "UWAGI",
        "REPORT"
    ]

    sheet_names = [
        sheet["properties"]["title"]
        for sheet in sheets["sheets"]
        if sheet["properties"]["title"] not in not_dev_st_list
    ]

    data = []

    for sheet_name in sheet_names:

        range_name = f"{sheet_name}!A1:ZZ"

        result = (
            service.spreadsheets()
            .values()
            .get(
                spreadsheetId=target_SPREADSHEET_ID,
                range=range_name
            )
            .execute()
        )

        values = result.get("values", [])

        if values:
            data.append(values)

    return data