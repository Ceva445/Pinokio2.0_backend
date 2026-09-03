from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base


class SiteDB(Base):
    """Довідник майданчиків (site).

    Замінює колишній enum SiteType: назви можна змінювати й додавати нові
    без міграцій. Пристрої посилаються на site через FK, тому перейменування
    майданчика автоматично відображається на всіх його пристроях.
    """

    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    devices = relationship("DeviceDB", back_populates="site")
