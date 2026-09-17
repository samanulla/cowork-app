"""Audit logging helper. Thin wrapper around the AuditLog model."""
from __future__ import annotations

import json
from typing import Any

from flask import request, has_request_context
from flask_login import current_user

from ..extensions import db
from ..models.audit import AuditLog


def record(action: str, entity_type: str, entity_id: int | None = None,
           details: dict[str, Any] | None = None) -> None:
    """Insert one audit row and commit."""
    actor_id = None
    ip = None
    ua = None
    if has_request_context():
        if current_user.is_authenticated:
            actor_id = current_user.id
        ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "")[:45]
        ua = (request.headers.get("User-Agent") or "")[:255]

    row = AuditLog(
        actor_id=actor_id, action=action,
        entity_type=entity_type, entity_id=entity_id,
        details=json.dumps(details, default=str) if details else None,
        ip_address=ip, user_agent=ua,
    )
    db.session.add(row)
    db.session.commit()
