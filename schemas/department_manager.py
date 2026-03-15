from pydantic import BaseModel

class DepartmentManagerOut(BaseModel):
    department: str
    email: str

    class Config:
        from_attributes = True