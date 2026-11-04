from typing import Optional
from pydantic import BaseModel
from schemas.device import DeviceOut

class EmployeeOut(BaseModel):
    first_name: str
    last_name: str
    company: str
    rfid: Optional[str] = None
    devices: list[DeviceOut] = []
    wms_login: Optional[str] = None
    expired: bool = False

    class Config:
        from_attributes = True
