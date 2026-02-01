from pydantic import BaseModel
from datetime import datetime
from enum import Enum
from typing import Optional
from schemas.user import UserOut
from schemas.device import DeviceOut

class DeviceChangeTransactionCreate(BaseModel):
    user_id: int
    device_id: int
    description: str


class DeviceChangeTransactionOut(BaseModel):
    id: int
    timestamp: datetime
    user: UserOut
    device: DeviceOut
    description: str

    class Config:
        from_attributes = True