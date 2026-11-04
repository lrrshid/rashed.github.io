"""Request bodies for projects, milestones, risks and issues."""
from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from pydantic import BeforeValidator

from ..models.project import HEALTH_NOTE_DIMENSIONS, MODEL_RELATIONS, RAGS, RISK_CATEGORIES, SEVERITIES
from .capability import StatusCode, _upper
from .common import (Amount, ApiModel, DateOnly, Id, PatchModel, Percent, Quantity, Reason, Version, code_text,
                     optional_text, required_text)

Name = required_text(2, 200)
Severity = Annotated[Literal[SEVERITIES], BeforeValidator(_upper)]  # type: ignore[valid-type]
RiskCategory = Annotated[Literal[RISK_CATEGORIES], BeforeValidator(_upper)]  # type: ignore[valid-type]
Relation = Annotated[Literal[MODEL_RELATIONS], BeforeValidator(_upper)]  # type: ignore[valid-type]
Rag = Annotated[Literal[RAGS], BeforeValidator(_upper)]  # type: ignore[valid-type]
Dimension = Annotated[Literal[HEALTH_NOTE_DIMENSIONS], BeforeValidator(_upper)]  # type: ignore[valid-type]


def _score(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise ValueError("Must be a whole number from 1 to 5.")
    return value


Score = Annotated[int, BeforeValidator(_score)]


class RequirementLink(ApiModel):
    requirement_id: Id
    quantity: Quantity


class ModelLink(ApiModel):
    model_id: Id
    relation: Relation


class _ProjectFields(ApiModel):
    stage_id: Id | None = None
    manager_name: optional_text(160) = None
    supplier_id: Id | None = None
    contract_id: Id | None = None
    budget: Amount = None
    committed: Amount = None
    actual_spend: Amount = None
    start_date: DateOnly = None
    baseline_end_date: DateOnly = None
    target_end_date: DateOnly = None
    forecast_end_date: DateOnly = None
    actual_end_date: DateOnly = None
    next_action_en: optional_text(2000) = None
    next_action_ar: optional_text(2000) = None
    notes_en: optional_text(4000) = None
    notes_ar: optional_text(4000) = None


class ProjectCreate(_ProjectFields):
    code: code_text(2, 20)
    name_en: Name
    name_ar: Name
    project_type_id: Id
    department_id: Id
    category_id: Id
    status_code: StatusCode
    progress_pct: Percent = 0
    requirements: list[RequirementLink] = []
    models: list[ModelLink] = []


class ProjectUpdate(_ProjectFields, PatchModel):
    REQUIRED_ON_PATCH: ClassVar[tuple[str, ...]] = ("name_en", "name_ar", "project_type_id", "department_id",
                                                    "category_id", "status_code", "progress_pct")
    name_en: Name | None = None
    name_ar: Name | None = None
    project_type_id: Id | None = None
    department_id: Id | None = None
    category_id: Id | None = None
    status_code: StatusCode | None = None
    progress_pct: Percent = None
    requirements: list[RequirementLink] | None = None
    models: list[ModelLink] | None = None
    reason: Reason = None
    version: Version | None = None

    def changes(self) -> dict[str, Any]:
        out = super().changes()
        out.pop("requirements", None)
        out.pop("models", None)
        return out


class HealthNoteUpdate(ApiModel):
    rag: Rag
    reason_en: optional_text(2000) = None
    reason_ar: optional_text(2000) = None
    reason: Reason = None


class _MilestoneFields(ApiModel):
    stage_id: Id | None = None
    owner_name: optional_text(160) = None
    actual_end_date: DateOnly = None
    forecast_end_date: DateOnly = None
    progress_pct: Percent = 0
    is_major: bool = False
    sort_order: int = 0


class MilestoneCreate(_MilestoneFields):
    project_id: Id
    name_en: Name
    name_ar: Name
    planned_start_date: DateOnly
    planned_end_date: DateOnly
    status_code: StatusCode


class MilestoneUpdate(_MilestoneFields, PatchModel):
    REQUIRED_ON_PATCH: ClassVar[tuple[str, ...]] = ("name_en", "name_ar", "planned_start_date", "planned_end_date",
                                                    "status_code")
    name_en: Name | None = None
    name_ar: Name | None = None
    planned_start_date: DateOnly = None
    planned_end_date: DateOnly = None
    status_code: StatusCode | None = None
    progress_pct: Percent = None
    is_major: bool | None = None
    sort_order: int | None = None
    reason: Reason = None
    version: Version | None = None


class _RiskFields(ApiModel):
    owner_name: optional_text(160) = None
    mitigation_en: optional_text(2000) = None
    mitigation_ar: optional_text(2000) = None
    mitigation_due_date: DateOnly = None


class RiskCreate(_RiskFields):
    code: code_text(2, 20)
    project_id: Id
    title_en: required_text(2, 500)
    title_ar: required_text(2, 500)
    category: RiskCategory
    probability: Score
    impact: Score
    status_code: StatusCode


class RiskUpdate(_RiskFields, PatchModel):
    REQUIRED_ON_PATCH: ClassVar[tuple[str, ...]] = ("title_en", "title_ar", "category", "probability", "impact",
                                                    "status_code")
    title_en: required_text(2, 500) | None = None
    title_ar: required_text(2, 500) | None = None
    category: RiskCategory | None = None
    probability: Score | None = None
    impact: Score | None = None
    status_code: StatusCode | None = None
    reason: Reason = None
    version: Version | None = None


class _IssueFields(ApiModel):
    owner_name: optional_text(160) = None
    raised_date: DateOnly = None
    target_date: DateOnly = None
    is_escalated: bool = False
    resolution_en: optional_text(2000) = None
    resolution_ar: optional_text(2000) = None


class IssueCreate(_IssueFields):
    code: code_text(2, 20)
    project_id: Id
    title_en: required_text(2, 500)
    title_ar: required_text(2, 500)
    severity: Severity
    status_code: StatusCode


class IssueUpdate(_IssueFields, PatchModel):
    REQUIRED_ON_PATCH: ClassVar[tuple[str, ...]] = ("title_en", "title_ar", "severity", "status_code", "raised_date")
    title_en: required_text(2, 500) | None = None
    title_ar: required_text(2, 500) | None = None
    severity: Severity | None = None
    status_code: StatusCode | None = None
    is_escalated: bool | None = None
    reason: Reason = None
    version: Version | None = None
