from pydantic import BaseModel

class GuestSchema(BaseModel):
    rfid: str
    name: str
    used: bool