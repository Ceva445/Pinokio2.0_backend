from sqlalchemy.orm import mapped_column, Mapped
from db.base import Base
from sqlalchemy import String

class DBGuest(Base):
    __tablename__ = 'guests'

    id: Mapped[int] = mapped_column(primary_key=True)
    rfid: Mapped[str] = mapped_column(unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    used: Mapped[bool] = mapped_column(default=False, nullable=False)