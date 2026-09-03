from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base


class DepartmentManagerDB(Base):
    __tablename__ = "department_managers"

    id: Mapped[int] = mapped_column(primary_key=True)
    department: Mapped[str] = mapped_column(index=True)
    email: Mapped[str]
    # Майданчик, за який відповідає керівник (довідник sites)
    site_id: Mapped[int | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )

    site = relationship("SiteDB", back_populates="department_managers")