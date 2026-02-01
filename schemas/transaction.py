from pydantic import BaseModel
from datetime import datetime
from enum import Enum
from typing import Optional
from schemas.employee import EmployeeOut
from schemas.device import DeviceOut


class TransactionType(str, Enum):
    registered = "registered"
    unregistered = "unregistered"


class TransactionCreate(BaseModel):
    employee_id: Optional[int] = None
    device_id: Optional[int] = None
    type: TransactionType


class TransactionOut(BaseModel):
    id: int
    timestamp: datetime
    type: TransactionType
    employee: Optional[EmployeeOut] = None
    device: Optional[DeviceOut] = None

    class Config:
        from_attributes = True