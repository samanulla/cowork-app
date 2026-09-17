"""Admin route: paginated audit log viewer + CSV export (super admin only)."""
from __future__ import annotations

import csv
from io import StringIO
from datetime import datetime

from flask import render_template, request, Response

from ...models import AuditLog, User
from ...utils.decorators import super_admin_required


def _apply_filters(q):
    action = (request.args.get("action") or "").strip()
    actor = (request.args.get("actor") or "").strip()
    date_from = (request.args.get("from") or "").strip()
    date_to = (request.args.get("to") or "").strip()
    if action:
        q = q.filter(AuditLog.action.ilike(f"%{action}%"))
    if actor:
        q = q.join(User, User.id == AuditLog.actor_id) \
             .filter(User.email.ilike(f"%{actor}%"))
    if date_from:
        try:
            q = q.filter(AuditLog.created_at >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(AuditLog.created_at <= datetime.fromisoformat(date_to))
        except ValueError:
            pass
    return q


def register_audit_routes(bp):

    @bp.route("/audit-log")
    @super_admin_required
    def audit_log():
        page = request.args.get("page", 1, type=int)
        q = AuditLog.query.order_by(AuditLog.created_at.desc())
        q = _apply_filters(q)
        pagination = q.paginate(page=page, per_page=50, error_out=False)
        return render_template("admin/audit_log.html", pagination=pagination,
                               filters={"action": request.args.get("action", ""),
                                        "actor": request.args.get("actor", ""),
                                        "from": request.args.get("from", ""),
                                        "to": request.args.get("to", "")})

    @bp.route("/audit-log.csv")
    @super_admin_required
    def audit_log_csv():
        q = AuditLog.query.order_by(AuditLog.created_at.desc())
        q = _apply_filters(q).limit(10000)
        buf = StringIO()
        w = csv.writer(buf)
        w.writerow(["created_at", "actor_email", "action", "entity_type",
                    "entity_id", "ip_address"])
        for row in q:
            w.writerow([
                row.created_at.isoformat() if row.created_at else "",
                (row.actor.email if row.actor else ""),
                row.action or "",
                row.entity_type or "",
                row.entity_id or "",
                row.ip_address or "",
            ])
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition":
                                 "attachment; filename=audit-log.csv"})
