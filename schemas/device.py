from pydantic import BaseModel
from enum import Enum

class DeviceType(str, Enum):
    scanner = "scanner"
    printer = "printer"

class DeviceOut(BaseModel):
    name: str
    rfid: str
    serial_number: str
    type: DeviceType
    enabled: bool

    class Config:
        from_attributes = True
