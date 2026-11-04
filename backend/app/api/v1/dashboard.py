"""GET /dashboard: the executive capability position."""
from __future__ import annotations

from flask import jsonify, request

from ...core.database import write_intent
from ...schemas.common import Query
from ...security.auth import PERM_VIEW, permission_required
from ...services import dashboard_service, snapshot_service
from . import bp, user


@bp.get("/dashboard")
@permission_required(PERM_VIEW)
def get_dashboard():
    query = Query(request.args, {"department"})
    department_id = query.id("department")
    if not snapshot_service.has_today():
        # The first view of the day stores today's KPI snapshot (trends); a write, so take the write lock first.
        from ...extensions import db
        db.session().rollback()
        with write_intent():
            if not snapshot_service.has_today():
                snapshot_service.take(_snapshot_actor())
            db.session().commit()
    return jsonify(dashboard_service.dashboard(user(), department_id))


def _snapshot_actor():
    """Snapshots are always taken for every department, whoever opens the dashboard first: computed as a
    system administrator would see them (department scopes are applied when they are read)."""
    from sqlalchemy import select

    from ...models import ROLE_SYS_ADMIN, AppUser
    from ...services import context
    admin = context.session().scalar(select(AppUser).where(AppUser.role_code == ROLE_SYS_ADMIN,
                                                           AppUser.is_active == 1).order_by(AppUser.id))
    return admin or user()
