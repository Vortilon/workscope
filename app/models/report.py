"""Stored report snapshots and metadata."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProjectReport(Base):
    __tablename__ = "project_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(32), default="main")
    summary_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    file_path: Mapped[str] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
