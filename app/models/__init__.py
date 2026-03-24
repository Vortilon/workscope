"""SQLAlchemy models. Import all here for Alembic."""
from app.models.audit import AuditLog
from app.models.user import User
from app.models.mpd import MPDDataset, MPDTask
from app.models.operator import Operator
from app.models.aircraft_type import AircraftType, EngineType
from app.models.project import (
    ApplicabilityCondition,
    ConditionAnswerHistory,
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
    WorkscopeImportRow,
)
from app.models.report import ProjectReport
from app.models.aviation_document import AviationDocument, AviationDocumentTask, AviationDocumentPart

__all__ = [
    "User",
    "Operator",
    "AircraftType",
    "EngineType",
    "MPDDataset",
    "MPDTask",
    "Project",
    "ProjectCheck",
    "ProjectFile",
    "ParsedWorkscopeRow",
    "WorkscopeMatchCandidate",
    "WorkscopeMatch",
    "WorkscopeImportRow",
    "ApplicabilityCondition",
    "ProjectConditionAnswer",
    "ConditionAnswerHistory",
    "ModificationEvidenceFile",
    "ProjectReport",
    "AuditLog",
    "AviationDocument",
    "AviationDocumentTask",
    "AviationDocumentPart",
]
