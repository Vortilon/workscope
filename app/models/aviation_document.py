from __future__ import annotations

from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AviationDocument(Base):
    __tablename__ = "aviation_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # uuid string
    document_key: Mapped[str] = mapped_column(String(256), index=True)  # groups revisions
    revision_index: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    source_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1024), nullable=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    parsed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), default="low", nullable=False)  # high|medium|low
    parse_warnings: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    header_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    totals_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    raw_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tasks: Mapped[list["AviationDocumentTask"]] = relationship(
        "AviationDocumentTask", back_populates="document", cascade="all, delete-orphan"
    )
    parts: Mapped[list["AviationDocumentPart"]] = relationship(
        "AviationDocumentPart", back_populates="document", cascade="all, delete-orphan"
    )


class AviationDocumentTask(Base):
    __tablename__ = "aviation_document_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("aviation_documents.id", ondelete="CASCADE"), index=True)

    section_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)

    service_interval: Mapped[str] = mapped_column(String(256), nullable=True, index=True)
    task_reference: Mapped[str] = mapped_column(String(256), nullable=True, index=True)
    ata_chapter: Mapped[str] = mapped_column(String(16), nullable=True, index=True)
    ata_derived: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    description: Mapped[str] = mapped_column(Text, nullable=True)
    man_hours: Mapped[float] = mapped_column(Float, nullable=True)
    task_type: Mapped[str] = mapped_column(String(32), nullable=True, index=True)
    ad_reference: Mapped[str] = mapped_column(String(256), nullable=True)

    component_pn: Mapped[str] = mapped_column(String(256), nullable=True)
    component_sn: Mapped[str] = mapped_column(String(256), nullable=True)
    component_position: Mapped[str] = mapped_column(String(64), nullable=True)
    component_description: Mapped[str] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(128), nullable=True)

    raw_line: Mapped[str] = mapped_column(Text, nullable=True)
    extra_fields: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    document: Mapped["AviationDocument"] = relationship("AviationDocument", back_populates="tasks")


class AviationDocumentPart(Base):
    __tablename__ = "aviation_document_parts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("aviation_documents.id", ondelete="CASCADE"), index=True)

    task_reference: Mapped[str] = mapped_column(String(256), nullable=True, index=True)
    part_number: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    part_type: Mapped[str] = mapped_column(String(64), nullable=True)
    unit: Mapped[str] = mapped_column(String(64), nullable=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=True)

    raw_line: Mapped[str] = mapped_column(Text, nullable=True)
    extra_fields: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    document: Mapped["AviationDocument"] = relationship("AviationDocument", back_populates="parts")
