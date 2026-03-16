"""Parsed workscope rows and match candidates/results. Per-project data only."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, Integer, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ParsedWorkscopeRow(Base):
    __tablename__ = "parsed_workscope_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    project_file_id: Mapped[int] = mapped_column(ForeignKey("project_files.id"), nullable=True)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sheet_index: Mapped[int] = mapped_column(Integer, nullable=True)
    # Detected/mapped columns – raw values
    task_ref_raw: Mapped[str] = mapped_column(String(256), nullable=True)
    service_check_raw: Mapped[str] = mapped_column(String(256), nullable=True)
    description_raw: Mapped[str] = mapped_column(Text, nullable=True)
    reference_raw: Mapped[str] = mapped_column(String(512), nullable=True)
    raw_row_json: Mapped[dict] = mapped_column(JSON, nullable=True)  # preserve full row
    row_type: Mapped[str] = mapped_column(String(32), nullable=True)  # task | header | empty | unknown
    confidence: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="parsed_rows")


class WorkscopeMatchCandidate(Base):
    __tablename__ = "workscope_match_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parsed_row_id: Mapped[int] = mapped_column(ForeignKey("parsed_workscope_rows.id", ondelete="CASCADE"), nullable=False)
    mpd_task_id: Mapped[int] = mapped_column(ForeignKey("mpd_tasks.id"), nullable=True)
    match_type: Mapped[str] = mapped_column(String(32), nullable=False)  # exact | normalized | pattern | ai_suggested
    confidence: Mapped[float] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(String(512), nullable=True)
    requires_confirmation: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WorkscopeMatch(Base):
    __tablename__ = "workscope_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    parsed_row_id: Mapped[int] = mapped_column(ForeignKey("parsed_workscope_rows.id", ondelete="CASCADE"), nullable=False)
    mpd_task_id: Mapped[int] = mapped_column(ForeignKey("mpd_tasks.id"), nullable=True)  # null = unmatched
    match_type: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(String(512), nullable=True)
    # Applicability/effectivity for this task on this project
    applicability_status: Mapped[str] = mapped_column(String(16), default="TBC")  # YES | NO | TBC
    applicability_reason: Mapped[str] = mapped_column(String(512), nullable=True)
    applicability_raw: Mapped[str] = mapped_column(Text, nullable=True)
    user_confirmed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="matches")
