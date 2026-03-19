"""SQLAlchemy models. Import all here for Alembic."""
from app.models.audit import AuditLog
from app.models.user import User
from app.models.mpd import MPDDataset, MPDTask
from app.models.project import (
    ApplicabilityCondition,
    Project,
    ProjectCheck,
    ProjectConditionAnswer,
    ProjectFile,
    ModificationEvidenceFile,
)
from app.models.workscope import (
    ParsedWorkscopeRow,
    WorkscopeMatch,
    WorkscopeMatchCandidate,
)
from app.models.report import ProjectReport
from app.models.aviation_document import AviationDocument, AviationDocumentTask, AviationDocumentPart

__all__ = [
    "User",
    "MPDDataset",
    "MPDTask",
    "Project",
    "ProjectCheck",
    "ProjectFile",
    "ParsedWorkscopeRow",
    "WorkscopeMatchCandidate",
    "WorkscopeMatch",
    "ApplicabilityCondition",
    "ProjectConditionAnswer",
    "ModificationEvidenceFile",
    "ProjectReport",
    "AuditLog",
    "AviationDocument",
    "AviationDocumentTask",
    "AviationDocumentPart",
]
