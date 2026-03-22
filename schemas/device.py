from pydantic import BaseModel
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
    enabled: bool
    employee_wms_login: Optional[str] = None


    class Config:
        from_attributes = True
