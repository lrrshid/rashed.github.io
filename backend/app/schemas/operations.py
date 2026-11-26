"""Request bodies for tests, maintenance orders, AI capability and development opportunities."""
from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BeforeValidator

from ..models.capability import PRIORITIES
from ..models.operations import COMPLEXITIES, DEV_TYPES, MAINT_TYPES, TEST_TYPES
from .capability import StatusCode, _upper
from .common import (Amount, ApiModel, Count, DateOnly, Id, PatchModel, Percent, Reason, Version, code_text,
                     optional_text, required_text)

TestType = Annotated[Literal[TEST_TYPES], BeforeValidator(_upper)]  # type: ignore[valid-type]
MaintType = Annotated[Literal[MAINT_TYPES], BeforeValidator(_upper)]  # type: ignore[valid-type]
DevType = Annotated[Literal[DEV_TYPES], BeforeValidator(_upper)]  # type: ignore[valid-type]
Complexity = Annotated[Literal[COMPLEXITIES], BeforeValidator(_upper)]  # type: ignore[valid-type]
Priority = Annotated[Literal[PRIORITIES], BeforeValidator(_upper)]  # type: ignore[valid-type]
Title = required_text(2, 200)


class _TestFields(ApiModel):
    asset_id: Id | None = None
    project_id: Id | None = None
    site_id: Id | None = None
    unit_id: Id | None = None
    score: Percent = None
    result_en: optional_text(2000) = None
    result_ar: optional_text(2000) = None


class TestCreate(_TestFields):
    __test__ = False
    code: code_text(2, 20)
    title_en: Title
    title_ar: Title
    model_id: Id
    department_id: Id
    test_type: TestType
    test_date: DateOnly
    status_code: StatusCode


class TestUpdate(_TestFields, PatchModel):
    __test__ = False
    REQUIRED_ON_PATCH: ClassVar[tuple[str, ...]] = ("title_en", "title_ar", "model_id", "department_id", "test_type",
                                                    "test_date", "status_code")
    title_en: Title | None = None
    title_ar: Title | None = None
    model_id: Id | None = None
    department_id: Id | None = None
    test_type: TestType | None = None
    test_date: DateOnly = None
    status_code: StatusCode | None = None
    reason: Reason = None
    version: Version | None = None


class _GoldenFields(ApiModel):
    notes_en: optional_text(2000) = None
    notes_ar: optional_text(2000) = None


class GoldenTrialCreate(_GoldenFields):
    code: code_text(2, 20)
    title_en: Title
    title_ar: Title
    model_id: Id
    trial_date: DateOnly
    status_code: StatusCode


class GoldenTrialUpdate(_GoldenFields, PatchModel):
    REQUIRED_ON_PATCH: ClassVar[tuple[str, ...]] = ("title_en", "title_ar", "model_id", "trial_date", "status_code")
    title_en: Title | None = None
    title_ar: Title | None = None
    model_id: Id | None = None
    trial_date: DateOnly = None
    status_code: StatusCode | None = None
    reason: Reason = None
    version: Version | None = None


class _MaintFields(ApiModel):
    expected_end_date: DateOnly = None
    actual_end_date: DateOnly = None
    progress_pct: Percent = 0
    cost: Amount = None
    parts_shortage: bool = False
    parts_text: optional_text(500) = None
    performed_by: optional_text(160) = None
    entry_reason_en: optional_text(2000) = None
    entry_reason_ar: optional_text(2000) = None


class MaintenanceCreate(_MaintFields):
    code: code_text(2, 20)
    asset_id: Id
    maint_type: MaintType
    title_en: Title
    title_ar: Title
    status_code: StatusCode
    start_date: DateOnly


class MaintenanceUpdate(_MaintFields, PatchModel):
    REQUIRED_ON_PATCH: ClassVar[tuple[str, ...]] = ("maint_type", "title_en", "title_ar", "status_code", "start_date",
                                                    "progress_pct")
    maint_type: MaintType | None = None
    title_en: Title | None = None
    title_ar: Title | None = None
    status_code: StatusCode | None = None
    start_date: DateOnly = None
    progress_pct: Percent = None
    parts_shortage: bool | None = None
    reason: Reason = None
    version: Version | None = None


class ModelAiUpdate(ApiModel):
    technologies: list[str]
    reason: Reason = None


class AiCriterionUpdate(PatchModel):
    REQUIRED_ON_PATCH: ClassVar[tuple[str, ...]] = ("name_en", "name_ar", "min_supported")
    name_en: required_text(1, 120) | None = None
    name_ar: required_text(1, 120) | None = None
    description_en: optional_text(500) = None
    description_ar: optional_text(500) = None
    min_supported: Count = None
    required: list[str] | None = None
    reason: Reason = None
    version: Version | None = None


class _DevFields(ApiModel):
    benefit_en: optional_text(500) = None
    benefit_ar: optional_text(500) = None
    estimated_cost: Amount = None
    duration_months: Count = None
    project_id: Id | None = None


class DevelopmentCreate(_DevFields):
    code: code_text(2, 20)
    model_id: Id
    dev_type: DevType
    title_en: Title
    title_ar: Title
    status_code: StatusCode
    complexity: Complexity
    priority: Priority


class DevelopmentUpdate(_DevFields, PatchModel):
    REQUIRED_ON_PATCH: ClassVar[tuple[str, ...]] = ("model_id", "dev_type", "title_en", "title_ar", "status_code",
                                                    "complexity", "priority")
    model_id: Id | None = None
    dev_type: DevType | None = None
    title_en: Title | None = None
    title_ar: Title | None = None
    status_code: StatusCode | None = None
    complexity: Complexity | None = None
    priority: Priority | None = None
    reason: Reason = None
    version: Version | None = None
