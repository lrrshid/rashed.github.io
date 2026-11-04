"""Projects, milestones, risks, issues, strategic timeline."""
from __future__ import annotations

from flask import jsonify, request

from ...models import Issue, Milestone, Project, Risk
from ...schemas.capability import ArchiveRequest
from ...schemas.common import Query
from ...schemas.project import (HealthNoteUpdate, IssueCreate, IssueUpdate, MilestoneCreate, MilestoneUpdate,
                                ProjectCreate, ProjectUpdate, RiskCreate, RiskUpdate)
from ...security.auth import PERM_VIEW, permission_required
from ...services import project_service
from . import body, bp, created, user
from .admin import register_history
from .capabilities import _codes, id_list


def _project_department(entity):
    from ...services import context
    return context.session().get(Project, entity.project_id).department_id


register_history("PROJECT", Project, "Project")
register_history("MILESTONE", Milestone, "Milestone", _project_department)
register_history("RISK", Risk, "Risk", _project_department)
register_history("ISSUE", Issue, "Issue", _project_department)


def _project_filters(query: Query) -> dict:
    return {"q": query.text("q", 100), "department": id_list(query, "department"),
            "category": id_list(query, "category"), "type": id_list(query, "type"), "status": _codes(query, "status"),
            "view": query.choice("view", project_service.VIEWS), "health": _codes(query, "health"),
            "archived": query.boolean("archived")}


@bp.get("/projects")
@permission_required(PERM_VIEW)
def list_projects():
    query = Query(request.args, {"q", "department", "category", "type", "status", "view", "health", "archived"})
    return jsonify(project_service.portfolio(user(), _project_filters(query)))


@bp.get("/timeline")
@permission_required(PERM_VIEW)
def timeline():
    query = Query(request.args, {"q", "department", "category", "type", "status", "view", "health"})
    return jsonify(project_service.timeline(user(), _project_filters(query)))


@bp.get("/projects/next-code")
@permission_required(PERM_VIEW)
def next_codes():
    Query(request.args, set())
    return jsonify({"project": project_service.next_code(Project, "PRJ"), "risk": project_service.next_code(Risk, "RSK"),
                    "issue": project_service.next_code(Issue, "ISS")})


@bp.get("/projects/<int:project_id>")
@permission_required(PERM_VIEW)
def get_project(project_id: int):
    Query(request.args, set())
    return jsonify(project_service.get_project(user(), project_id))


@bp.post("/projects")
def create_project():
    result = project_service.create_project(user(), ProjectCreate.model_validate(body()))
    return created(result, f"/api/v1/projects/{result['id']}")


@bp.patch("/projects/<int:project_id>")
def update_project(project_id: int):
    return jsonify(project_service.update_project(user(), project_id, ProjectUpdate.model_validate(body())))


@bp.put("/projects/<int:project_id>/health/<dimension>")
def put_health_note(project_id: int, dimension: str):
    data = HealthNoteUpdate.model_validate(body())
    dim = dimension.upper()
    if dim not in ("SCOPE", "PROCUREMENT"):
        from ...exceptions import NotFound
        raise NotFound("Only the scope and procurement indicators are recorded by hand.")
    return jsonify(project_service.set_health_note(user(), project_id, dim, data.rag, data.reason_en, data.reason_ar,
                                                   data.reason))


@bp.post("/projects/<int:project_id>/archive")
def archive_project(project_id: int):
    data = ArchiveRequest.model_validate(body())
    return jsonify(project_service.archive_project(user(), project_id, data.archived, data.version, data.reason))


def _child_filters(query: Query) -> dict:
    return {"project": id_list(query, "project"), "department": id_list(query, "department"),
            "status": _codes(query, "status"), "level": _codes(query, "level"), "severity": _codes(query, "severity"),
            "majorOnly": query.boolean("majorOnly")}


_CHILD_PARAMS = {"project", "department", "status", "level", "severity", "majorOnly"}


@bp.get("/milestones")
@permission_required(PERM_VIEW)
def list_milestones():
    return jsonify(project_service.list_milestones(user(), _child_filters(Query(request.args, _CHILD_PARAMS))))


@bp.post("/milestones")
def create_milestone():
    result = project_service.save_milestone(user(), MilestoneCreate.model_validate(body()))
    return created(result, f"/api/v1/milestones/{result['id']}")


@bp.patch("/milestones/<int:milestone_id>")
def update_milestone(milestone_id: int):
    return jsonify(project_service.save_milestone(user(), MilestoneUpdate.model_validate(body()), milestone_id))


@bp.get("/risks")
@permission_required(PERM_VIEW)
def list_risks():
    return jsonify(project_service.list_risks(user(), _child_filters(Query(request.args, _CHILD_PARAMS))))


@bp.post("/risks")
def create_risk():
    result = project_service.save_risk(user(), RiskCreate.model_validate(body()))
    return created(result, f"/api/v1/risks/{result['id']}")


@bp.patch("/risks/<int:risk_id>")
def update_risk(risk_id: int):
    return jsonify(project_service.save_risk(user(), RiskUpdate.model_validate(body()), risk_id))


@bp.get("/issues")
@permission_required(PERM_VIEW)
def list_issues():
    return jsonify(project_service.list_issues(user(), _child_filters(Query(request.args, _CHILD_PARAMS))))


@bp.post("/issues")
def create_issue():
    result = project_service.save_issue(user(), IssueCreate.model_validate(body()))
    return created(result, f"/api/v1/issues/{result['id']}")


@bp.patch("/issues/<int:issue_id>")
def update_issue(issue_id: int):
    return jsonify(project_service.save_issue(user(), IssueUpdate.model_validate(body()), issue_id))

