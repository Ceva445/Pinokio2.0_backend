from sqlalchemy.orm import Mapped, mapped_column
from db.base import Base


class DepartmentManagerDB(Base):
    __tablename__ = "department_managers"

    id: Mapped[int] = mapped_column(primary_key=True)
    department: Mapped[str] = mapped_column(index=True)
    email: Mapped[str]