from pydantic import BaseModel, field_validator
from enum import Enum
from typing import Optional

class DeviceType(str, Enum):
    scanner = "scanner"
    printer = "printer"

class DeviceOut(BaseModel):
    name: str
    rfid: str
    serial_number: str
    type: DeviceType
    site: Optional[str] = None      # назва site з довідника (sites.name)
    enabled: bool
    employee_wms_login: Optional[str] = None

    @field_validator("site", mode="before")
    @classmethod
    def site_to_name(cls, value):
        """site у моделі — обʼєкт SiteDB; назовні віддаємо його назву."""
        if value is None or isinstance(value, str):
            return value
        return getattr(value, "name", None)

    class Config:
        from_attributes = True
