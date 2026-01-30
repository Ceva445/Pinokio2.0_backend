from typing import Optional
from pydantic import BaseModel
from schemas.device import DeviceOut

class EmployeeOut(BaseModel):
    first_name: str
    last_name: str
    company: str
    rfid: str
    devices: list[DeviceOut] = []
    wms_login: Optional[str] = None

    class Config:
        from_attributes = True
