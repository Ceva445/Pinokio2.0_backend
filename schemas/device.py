from pydantic import BaseModel
from enum import Enum
from typing import Optional

class DeviceType(str, Enum):
    scanner = "scanner"
    printer = "printer"

class SiteType(str, Enum):
    EMAG = "EMAG"
    XD = "XD"
    STOCK = "STOCK"
    KONTROLA = "KONTROLA"
    PRZYJECIA_445 = "PRZYJECIA_445"

class DeviceOut(BaseModel):
    name: str
    rfid: str
    serial_number: str
    type: DeviceType
    site: SiteType
    enabled: bool
    employee_wms_login: Optional[str] = None


    class Config:
        from_attributes = True
