"""ORM entities. Tables are created by the versioned SQL scripts in db/, never by create_all()."""
from .base import Base
from .security import (ROLE_SYS_ADMIN, AppRole, AppSession, AppSetting, AppUser, AuditEvent, RolePermission,
                       SavedView, UserDepartment)
from .lists import (CapabilityCategory, Department, Organization, ProjectType, Site, SpecField, StatusDef,
                    WorkflowStage)
from .capability import (Asset, AssetStatusHistory, CapabilityModel, CapabilityRequirement, Contract, MetricSnapshot,
                         RequirementModel)
from .project import Issue, Milestone, Project, ProjectHealthNote, ProjectModel, ProjectRequirement, Risk
from .operations import (AiLevelCriterion, AiTechnology, DevelopmentOpportunity, MaintenanceOrder, ModelAiTech,
                         TestEvent)
from .documents import AlertAck, AlertRule, Document, DocumentVersion
from .reports import ReportRun, ReportSchedule, ReportTemplate

__all__ = [
    "Base", "ROLE_SYS_ADMIN", "AppRole", "AppSession", "AppSetting", "AppUser", "AuditEvent", "RolePermission",
    "SavedView", "UserDepartment", "CapabilityCategory", "Department", "Organization", "ProjectType", "Site",
    "SpecField", "StatusDef", "WorkflowStage", "Asset", "AssetStatusHistory", "CapabilityModel",
    "CapabilityRequirement", "Contract", "MetricSnapshot", "RequirementModel", "Issue", "Milestone", "Project",
    "ProjectHealthNote", "ProjectModel", "ProjectRequirement", "Risk", "AiLevelCriterion", "AiTechnology",
    "DevelopmentOpportunity", "MaintenanceOrder", "ModelAiTech", "TestEvent", "AlertAck", "AlertRule", "Document",
    "DocumentVersion", "ReportRun", "ReportSchedule", "ReportTemplate",
]
