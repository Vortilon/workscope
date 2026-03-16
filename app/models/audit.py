"""Audit log for sanitization and sensitive operations."""
from datetime import datetime
from sqlalchemy import DateTime, String, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=True)
    details: Mapped[str] = mapped_column(Text, nullable=True)
    # For AI: what was sanitized and sent (never raw confidential data)
    sanitized_payload_summary: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
