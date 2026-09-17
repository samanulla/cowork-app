from .routes import admin_bp
from .staff_routes import register_staff_routes
from .expense_routes import register_expense_routes
from .billing_routes import register_billing_routes
from .email_routes import register_email_template_routes
from .report_routes import register_report_routes
from .settings_routes import register_settings_routes
from .audit_routes import register_audit_routes

register_staff_routes(admin_bp)
register_expense_routes(admin_bp)
register_billing_routes(admin_bp)
register_email_template_routes(admin_bp)
register_report_routes(admin_bp)
register_settings_routes(admin_bp)
register_audit_routes(admin_bp)

__all__ = ["admin_bp"]
