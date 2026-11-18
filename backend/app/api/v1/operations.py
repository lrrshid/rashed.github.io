"""Testing & evaluation, maintenance, AI capability, development potential, decision support."""
from __future__ import annotations

from flask import jsonify, request

from ...models import Asset, DevelopmentOpportunity, MaintenanceOrder, TestEvent
from ...schemas.common import Query
from ...schemas.operations import (AiCriterionUpdate, DevelopmentCreate, DevelopmentUpdate, MaintenanceCreate,
                                   MaintenanceUpdate, ModelAiUpdate, TestCreate, TestUpdate)
from ...security.auth import PERM_VIEW, permission_required
from ...services import context, operations_service, project_service, search_service, testing_service
from . import body, bp, created, user
from .admin import register_history
from .capabilities import _codes, id_list

register_history("TEST_EVENT", TestEvent, "Test")
register_history("MAINTENANCE_ORDER", MaintenanceOrder, "Maintenance order",
                 lambda e: context.session().get(Asset, e.asset_id).department_id)
register_history("DEVELOPMENT_OPPORTUNITY", DevelopmentOpportunity, "Development opportunity")


@bp.get("/tests")
@permission_required(PERM_VIEW)
def list_tests():
    q = Query(request.args, {"model", "project", "department", "unit", "asset", "status", "type"})
    return jsonify(testing_service.list_tests(user(), {
        "model": id_list(q, "model"), "project": id_list(q, "project"), "department": id_list(q, "department"),
        "unit": id_list(q, "unit"),
        "asset": id_list(q, "asset"), "status": _codes(q, "status"), "type": q.choice("type", ("INTERNAL", "EXTERNAL"))}))


@bp.post("/tests")
def create_test():
    result = testing_service.save_test(user(), TestCreate.model_validate(body()))
    return created(result, f"/api/v1/tests/{result['id']}")


@bp.patch("/tests/<int:test_id>")
def update_test(test_id: int):
    return jsonify(testing_service.save_test(user(), TestUpdate.model_validate(body()), test_id))


@bp.get("/maintenance")
@permission_required(PERM_VIEW)
def list_maintenance():
    q = Query(request.args, {"department", "status", "type", "asset"})
    return jsonify(operations_service.maintenance(user(), {
        "department": id_list(q, "department"), "status": _codes(q, "status"), "asset": id_list(q, "asset"),
        "type": q.choice("type", ("PREVENTIVE", "CORRECTIVE", "INSPECTION", "UPGRADE"))}))


@bp.post("/maintenance")
def create_maintenance():
    result = operations_service.save_maintenance(user(), MaintenanceCreate.model_validate(body()))
    return created(result, f"/api/v1/maintenance/{result['id']}")


@bp.patch("/maintenance/<int:order_id>")
def update_maintenance(order_id: int):
    return jsonify(operations_service.save_maintenance(user(), MaintenanceUpdate.model_validate(body()), order_id))


@bp.get("/ai")
@permission_required(PERM_VIEW)
def ai_overview():
    Query(request.args, set())
    return jsonify(operations_service.ai_overview(user()))


@bp.get("/models/<int:model_id>/ai")
@permission_required(PERM_VIEW)
def model_ai(model_id: int):
    Query(request.args, set())
    return jsonify(operations_service.model_ai(user(), model_id))


@bp.put("/models/<int:model_id>/ai")
def put_model_ai(model_id: int):
    data = ModelAiUpdate.model_validate(body())
    return jsonify(operations_service.set_model_ai(user(), model_id, [c.strip().upper() for c in data.technologies],
                                                   data.reason))


@bp.patch("/ai/levels/<int:level>")
def update_ai_level(level: int):
    return jsonify(operations_service.update_ai_criterion(user(), level, AiCriterionUpdate.model_validate(body())))


@bp.get("/development")
@permission_required(PERM_VIEW)
def list_development():
    q = Query(request.args, {"model", "status", "type"})
    return jsonify(operations_service.development(user(), {
        "model": id_list(q, "model"), "status": _codes(q, "status"), "type": (q.text("type", 20) or "").upper() or None}))


@bp.post("/development")
def create_development():
    result = operations_service.save_development(user(), DevelopmentCreate.model_validate(body()))
    return created(result, f"/api/v1/development/{result['id']}")


@bp.patch("/development/<int:opp_id>")
def update_development(opp_id: int):
    return jsonify(operations_service.save_development(user(), DevelopmentUpdate.model_validate(body()), opp_id))


@bp.get("/decision-support")
@permission_required(PERM_VIEW)
def decision_support():
    Query(request.args, set())
    return jsonify(operations_service.decision_support(user()))


@bp.get("/operations/next-code")
@permission_required(PERM_VIEW)
def operations_next_codes():
    Query(request.args, set())
    return jsonify({"test": project_service.next_code(TestEvent, "TST"),
                    "maintenance": project_service.next_code(MaintenanceOrder, "MNT"),
                    "development": project_service.next_code(DevelopmentOpportunity, "DEV")})



def _search_tests(actor, q):
    from ...services.search_service import _like
    from sqlalchemy import select as _select
    query = testing_service._scoped(actor, _select(TestEvent).where(
        TestEvent.archived_at.is_(None), _like(TestEvent.code, TestEvent.title_en, TestEvent.title_ar, q=q)))
    return "tests", [testing_service.test_dto(e) for e in context.session().scalars(query.limit(25))]


def _search_maintenance(actor, q):
    from ...services.search_service import _like
    from sqlalchemy import select as _select
    query = operations_service._asset_scope(actor, _select(MaintenanceOrder, Asset).join(Asset, Asset.id == MaintenanceOrder.asset_id)
                                            .where(MaintenanceOrder.archived_at.is_(None),
                                                   _like(MaintenanceOrder.code, MaintenanceOrder.title_en,
                                                         MaintenanceOrder.title_ar, Asset.code, q=q)))
    return "maintenance", [operations_service.maintenance_dto(m, a) for m, a in context.session().execute(query.limit(25))]


search_service.register(_search_tests)
search_service.register(_search_maintenance)
