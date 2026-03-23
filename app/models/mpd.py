"""MPD datasets and tasks. Static MPD data – do not modify after import except via re-import."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, Integer, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MPDDataset(Base):
    __tablename__ = "mpd_datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    manufacturer: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    revision: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(128), nullable=True)
    source_file: Mapped[str] = mapped_column(String(512), nullable=True)
    parsed_status: Mapped[str] = mapped_column(String(32), default="pending")  # pending | in_progress | done | error
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tasks: Mapped[list["MPDTask"]] = relationship("MPDTask", back_populates="dataset", cascade="all, delete-orphan")


class MPDTask(Base):
    __tablename__ = "mpd_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("mpd_datasets.id", ondelete="CASCADE"), nullable=False, index=True)

    # Core identifiers — mpd_item_number is the primary key from the manufacturer's document
    mpd_item_number: Mapped[str] = mapped_column(String(256), nullable=True, index=True)
    task_reference: Mapped[str] = mapped_column(String(256), nullable=True, index=True)
    task_number: Mapped[str] = mapped_column(String(128), nullable=True, index=True)
    task_code: Mapped[str] = mapped_column(String(128), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    # Structure
    section: Mapped[str] = mapped_column(String(128), nullable=True)
    chapter: Mapped[str] = mapped_column(String(128), nullable=True)

    # Intervals – raw and normalized (preserve both)
    threshold_raw: Mapped[str] = mapped_column(String(256), nullable=True)
    interval_raw: Mapped[str] = mapped_column(String(256), nullable=True)
    threshold_normalized: Mapped[str] = mapped_column(String(256), nullable=True)
    interval_normalized: Mapped[str] = mapped_column(String(256), nullable=True)
    # Machine-readable interval structure (e.g. {"value": 24, "unit": "MO"})
    interval_json: Mapped[dict] = mapped_column(JSON, nullable=True)

    source_references: Mapped[str] = mapped_column(String(512), nullable=True)  # MRBR / CPCP / MPD etc.

    # Applicability – raw and normalized tokens
    applicability_raw: Mapped[str] = mapped_column(Text, nullable=True)
    applicability_tokens_normalized: Mapped[str] = mapped_column(Text, nullable=True)  # JSON array or structured

    # Job / procedure / references
    job_procedure: Mapped[str] = mapped_column(String(512), nullable=True)
    mp_reference: Mapped[str] = mapped_column(String(256), nullable=True)
    cmm_reference: Mapped[str] = mapped_column(String(256), nullable=True)

    # Zones, access, prep, skill, equipment
    zones: Mapped[str] = mapped_column(String(512), nullable=True)
    zone_mh: Mapped[str] = mapped_column(String(64), nullable=True)
    man: Mapped[str] = mapped_column(String(64), nullable=True)
    access_items: Mapped[str] = mapped_column(String(512), nullable=True)
    access_mh: Mapped[str] = mapped_column(String(64), nullable=True)
    preparation_description: Mapped[str] = mapped_column(Text, nullable=True)
    preparation_mh: Mapped[str] = mapped_column(String(64), nullable=True)
    skill: Mapped[str] = mapped_column(String(128), nullable=True)
    equipment: Mapped[str] = mapped_column(String(512), nullable=True)

    # Preserve any extra manufacturer-specific fields as JSON
    extra_raw: Mapped[dict] = mapped_column(JSON, nullable=True)
    row_index: Mapped[int] = mapped_column(Integer, nullable=True)  # original sheet row

    dataset: Mapped["MPDDataset"] = relationship("MPDDataset", back_populates="tasks")
