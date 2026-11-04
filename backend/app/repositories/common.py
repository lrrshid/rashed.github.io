"""Query helpers shared by the services."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session


def like_pattern(text: str) -> str:
    """Case-insensitive 'contains' pattern with LIKE wildcards escaped (input is still a bound value)."""
    escaped = text.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def get(session: Session, model, entity_id: int, for_update: bool = False):
    """One row by id. for_update locks it (Oracle; SQLite already serialises writes) and re-reads it, so the
    version check that follows sees the committed row. `of=model.id`: Oracle renders a bare table as an empty
    FOR UPDATE OF list, which is a syntax error."""
    query = select(model).where(model.id == entity_id)
    if for_update:
        query = query.with_for_update(of=model.id).execution_options(populate_existing=True)
    return session.scalars(query).one_or_none()
