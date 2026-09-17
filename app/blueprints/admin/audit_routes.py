"""Admin route: paginated audit log viewer (super admin only)."""
from __future__ import annotations

from flask import render_template, request

from ...models import AuditLog
from ...utils.decorators import super_admin_required


def register_audit_routes(bp):

    @bp.route("/audit-log")
    @super_admin_required
    def audit_log():
        page = request.args.get("page", 1, type=int)
        pagination = (AuditLog.query
                      .order_by(AuditLog.created_at.desc())
                      .paginate(page=page, per_page=50, error_out=False))
        return render_template("admin/audit_log.html", pagination=pagination)
