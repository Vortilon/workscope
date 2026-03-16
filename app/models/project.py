"""Projects (one aircraft MSN), checks, files, applicability, evidence."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, Integer, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    manufacturer: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    mpd_dataset_id: Mapped[int] = mapped_column(ForeignKey("mpd_datasets.id"), nullable=True, index=True)
    msn: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tsn: Mapped[str] = mapped_column(String(64), nullable=True)
    csn: Mapped[str] = mapped_column(String(64), nullable=True)
    registration: Mapped[str] = mapped_column(String(32), nullable=True)
    selected_checks: Mapped[str] = mapped_column(Text, nullable=True)  # JSON array of check names/codes
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft | analysis | report
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    files: Mapped[list["ProjectFile"]] = relationship("ProjectFile", back_populates="project", cascade="all, delete-orphan")
    parsed_rows: Mapped[list["ParsedWorkscopeRow"]] = relationship(
        "ParsedWorkscopeRow", back_populates="project", cascade="all, delete-orphan", foreign_keys="ParsedWorkscopeRow.project_id"
    )
    matches: Mapped[list["WorkscopeMatch"]] = relationship(
        "WorkscopeMatch", back_populates="project", cascade="all, delete-orphan"
    )
    evidence_files: Mapped[list["ModificationEvidenceFile"]] = relationship(
        "ModificationEvidenceFile", back_populates="project", cascade="all, delete-orphan"
    )
    checks: Mapped[list["ProjectCheck"]] = relationship(
        "ProjectCheck", back_populates="project", cascade="all, delete-orphan"
    )


class ProjectCheck(Base):
    __tablename__ = "project_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    check_code: Mapped[str] = mapped_column(String(64), nullable=False)
    check_name: Mapped[str] = mapped_column(String(256), nullable=True)
    last_done_date: Mapped[str] = mapped_column(String(32), nullable=True)
    last_done_fh: Mapped[str] = mapped_column(String(32), nullable=True)
    last_done_fc: Mapped[str] = mapped_column(String(32), nullable=True)
    next_due_date: Mapped[str] = mapped_column(String(32), nullable=True)
    next_due_fh: Mapped[str] = mapped_column(String(32), nullable=True)
    next_due_fc: Mapped[str] = mapped_column(String(32), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="checks")


class ProjectFile(Base):
    __tablename__ = "project_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)  # workscope | modification_evidence | other
    original_name: Mapped[str] = mapped_column(String(256), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=True)
    sheet_index: Mapped[int] = mapped_column(Integer, nullable=True)
    parsed_status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="files")


class ApplicabilityCondition(Base):
    __tablename__ = "applicability_conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g. PRE 33844, POST YYY, CFM56
    raw_expression: Mapped[str] = mapped_column(Text, nullable=True)
    resolved: Mapped[str] = mapped_column(String(16), nullable=True)  # YES | NO | TBC
    evidence_file_id: Mapped[int] = mapped_column(ForeignKey("project_files.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProjectConditionAnswer(Base):
    __tablename__ = "project_condition_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    condition_token: Mapped[str] = mapped_column(String(128), nullable=False)
    answer: Mapped[str] = mapped_column(String(16), nullable=False)  # YES | NO | TBC
    source: Mapped[str] = mapped_column(String(64), nullable=True)  # user | evidence | system
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ModificationEvidenceFile(Base):
    __tablename__ = "modification_evidence_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    original_name: Mapped[str] = mapped_column(String(256), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)
    extracted_conditions: Mapped[dict] = mapped_column(JSON, nullable=True)  # candidate mod/config tokens
    validation_status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="evidence_files")
