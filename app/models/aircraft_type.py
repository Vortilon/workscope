"""AircraftType and EngineType catalogue tables."""
from datetime import datetime
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AircraftType(Base):
    """One row per aircraft variant (e.g. A320-214, 737-800)."""
    __tablename__ = "aircraft_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    manufacturer: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    series: Mapped[str] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    projects: Mapped[list] = relationship("Project", back_populates="aircraft_type")

    @property
    def display_name(self) -> str:
        return f"{self.manufacturer} – {self.model}"

    @property
    def display_name_with_series(self) -> str:
        if self.series and self.series != self.model:
            return f"{self.manufacturer} – {self.model} ({self.series})"
        return f"{self.manufacturer} – {self.model}"


class EngineType(Base):
    """One row per engine variant (e.g. CFM56-7B22)."""
    __tablename__ = "engine_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engine_family: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    engine_model: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    engine_manufacturer: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    projects: Mapped[list] = relationship("Project", back_populates="engine_type")

    @property
    def display_name(self) -> str:
        return f"{self.engine_manufacturer} – {self.engine_model}"

    @property
    def display_name_with_family(self) -> str:
        if self.engine_family and self.engine_family != self.engine_model:
            return f"{self.engine_manufacturer} – {self.engine_model} ({self.engine_family})"
        return f"{self.engine_manufacturer} – {self.engine_model}"
