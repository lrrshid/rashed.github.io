"""Golden-sample trials (Capabilities > Golden-sample trials): the trials of each capability model's reference unit,
with three attached scans each: the trial, the higher-level directive letter and the official trial form
(document_service.SLOTS). Statuses: the TEST list. Seen by everyone, like the capability models."""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select

from ..models import CapabilityModel, GoldenSampleTrial
from ..schemas.dto import record_meta, sid
from ..security.auth import PERM_EDIT_TESTING
from . import context, crud, document_service, lookup_service as lk

SLOTS = tuple(document_service.SLOTS["GOLDEN_SAMPLE_TRIAL"])
_FIELDS = ("title_en", "title_ar", "model_id", "trial_date", "status_code", "notes_en", "notes_ar")


def trial_dto(e: GoldenSampleTrial, files: dict | None = None) -> dict:
    return {"id": sid(e.id), "code": e.code, "titleEn": e.title_en, "titleAr": e.title_ar,
            "model": lk.ref_id(CapabilityModel, e.model_id), "trialDate": e.trial_date.isoformat(),
            "status": e.status_code, "notesEn": e.notes_en, "notesAr": e.notes_ar,
            "attachments": {slot: (files or {}).get(slot) for slot in SLOTS}, **record_meta(e)}


def list_trials(actor, f: dict) -> dict:
    query = select(GoldenSampleTrial).where(GoldenSampleTrial.archived_at.is_(None))
    if f.get("model"):
        query = query.where(GoldenSampleTrial.model_id.in_(f["model"]))
    if f.get("status"):
        query = query.where(GoldenSampleTrial.status_code.in_(f["status"]))
    rows = list(context.session().scalars(query.order_by(GoldenSampleTrial.trial_date.desc(), GoldenSampleTrial.code)))
    files = document_service.slot_status("GOLDEN_SAMPLE_TRIAL", [e.id for e in rows])
    status = Counter(e.status_code for e in rows)
    complete = sum(1 for e in rows if len(files.get(e.id, {})) == len(SLOTS))
    return {"items": [trial_dto(e, files.get(e.id)) for e in rows],
            "kpis": {"total": len(rows), "planned": status["PLANNED"],
                     "inProgress": status["IN_PROGRESS"] + status["AWAITING_RESULT"], "passed": status["PASSED"],
                     "conditional": status["CONDITIONAL"], "failed": status["FAILED"],
                     "complete": complete, "missing": len(rows) - complete}}


def _validate(values: dict, current: GoldenSampleTrial | None = None) -> None:
    if "model_id" in values:
        crud.check_ref(CapabilityModel, values["model_id"], "modelId", "Model",
                       current is not None and current.model_id == values["model_id"])
    if "status_code" in values:
        crud.check_status("TEST", values["status_code"], "status", current.status_code if current else None)


def save_trial(actor, data, trial_id: int | None = None) -> dict:
    if trial_id is None:
        values = {k: getattr(data, k) for k in _FIELDS}
        crud.check_unique_code(GoldenSampleTrial, data.code)
        _validate(values)
        e = GoldenSampleTrial(code=data.code, **values)
        crud.create(actor, e, PERM_EDIT_TESTING)
    else:
        e = crud.load(GoldenSampleTrial, trial_id, actor, "Golden-sample trial", for_update=True)
        changes = {k: v for k, v in data.changes().items() if k in _FIELDS}
        _validate(changes, e)
        crud.update(actor, e, changes, PERM_EDIT_TESTING, data.version, data.reason, department_ids=(None,))
    files = document_service.slot_status("GOLDEN_SAMPLE_TRIAL", [e.id])
    return trial_dto(e, files.get(e.id))
