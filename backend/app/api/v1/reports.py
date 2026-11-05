"""Reports: catalogue, run, export (CSV, Excel, PowerPoint), custom builder and templates, schedules, run history."""
from __future__ import annotations

from flask import Response, jsonify, request, send_file

from ...exceptions import ValidationFailed
from ...schemas.common import ApiModel, Query
from ...security.auth import PERM_EXPORT, PERM_REPORTS_VIEW, permission_required, require_permission
from ...services import report_export, report_service, schedule_service
from . import body, bp, created, user

LANG = ("EN", "AR", "BILINGUAL")


@bp.get("/reports")
@permission_required(PERM_REPORTS_VIEW)
def list_reports():
    Query(request.args, set())
    return jsonify({**report_service.list_reports(user()), "datasets": report_service.dataset_fields(),
                    "templates": report_service.list_templates(user())})


@bp.get("/reports/history")
@permission_required(PERM_REPORTS_VIEW)
def report_history():
    Query(request.args, set())
    return jsonify({"items": report_service.run_history(user())})


@bp.get("/reports/history/<int:run_id>/file")
@permission_required(PERM_REPORTS_VIEW)
def scheduled_file(run_id: int):
    """A file a scheduled report wrote to the reports folder (the owner of the schedule or an administrator)."""
    Query(request.args, set())
    run, path = schedule_service.stored_file(user(), run_id)
    return send_file(path, as_attachment=True, download_name=path.name, max_age=0)


@bp.get("/reports/<key>")
@permission_required(PERM_REPORTS_VIEW)
def run_report(key: str):
    q = Query(request.args, {"lang", "print"})
    fmt = "PRINT" if q.boolean("print") else "SCREEN"
    return jsonify(report_service.run_report(user(), key, q.choice("lang", LANG) or "EN", fmt))


@bp.get("/reports/<key>/export")
@permission_required(PERM_REPORTS_VIEW)
def export_report(key: str):
    require_permission(user(), PERM_EXPORT)
    q = Query(request.args, {"lang", "format"})
    lang = q.choice("lang", LANG) or "EN"
    fmt = q.choice("format", tuple(report_export.EXPORTERS)) or "XLSX"
    result = report_service.run_report(user(), key, lang, fmt, log=False)
    exporter, mimetype, ext = report_export.EXPORTERS[fmt]
    name = report_export.file_name(result, ext)
    content = exporter(result, lang)
    report_service.log_run(user(), result, lang, fmt, file_name=name)
    response = Response(content, mimetype=mimetype)
    response.headers["Content-Disposition"] = f'attachment; filename="{name}"'
    return response


class CustomRun(ApiModel):
    definition: dict
    lang: str = "EN"
    format: str | None = None


@bp.post("/reports/custom")
@permission_required(PERM_REPORTS_VIEW)
def run_custom():
    data = CustomRun.model_validate(body())
    lang = data.lang.upper() if data.lang and data.lang.upper() in LANG else "EN"
    result = report_service.run_custom(user(), data.definition, lang)
    if data.format:
        require_permission(user(), PERM_EXPORT)
        fmt = data.format.upper()
        if fmt not in report_export.EXPORTERS:
            raise ValidationFailed.field("format", "Must be CSV, XLSX or PPTX.")
        exporter, mimetype, ext = report_export.EXPORTERS[fmt]
        name = report_export.file_name(result, ext)
        report_service.log_run(user(), result, lang, fmt, file_name=name)
        response = Response(exporter(result, lang), mimetype=mimetype)
        response.headers["Content-Disposition"] = f'attachment; filename="{name}"'
        return response
    report_service.log_run(user(), result, lang, "SCREEN")
    return jsonify(result)


class TemplateSave(ApiModel):
    name: str
    definition: dict
    shared: bool = False
    version: int | None = None


@bp.post("/report-templates")
@permission_required(PERM_REPORTS_VIEW)
def create_template():
    data = TemplateSave.model_validate(body())
    if not 1 <= len(data.name.strip()) <= 120:
        raise ValidationFailed.field("name", "Must be 1 to 120 characters.")
    result = report_service.save_template(user(), data.name.strip(), data.definition, data.shared)
    return created(result, f"/api/v1/report-templates/{result['id']}")


@bp.put("/report-templates/<int:template_id>")
@permission_required(PERM_REPORTS_VIEW)
def update_template(template_id: int):
    data = TemplateSave.model_validate(body())
    return jsonify(report_service.save_template(user(), data.name.strip(), data.definition, data.shared, template_id,
                                                data.version))


@bp.get("/report-schedules")
@permission_required(PERM_REPORTS_VIEW)
def list_schedules():
    Query(request.args, set())
    return jsonify({"items": schedule_service.list_schedules(user())})


@bp.post("/report-schedules")
@permission_required(PERM_REPORTS_VIEW)
def create_schedule():
    result = schedule_service.save_schedule(user(), body())
    return created(result, f"/api/v1/report-schedules/{result['id']}")


@bp.patch("/report-schedules/<int:schedule_id>")
@permission_required(PERM_REPORTS_VIEW)
def update_schedule(schedule_id: int):
    return jsonify(schedule_service.save_schedule(user(), body(), schedule_id))
