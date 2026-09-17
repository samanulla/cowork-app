"""Auth decorators for role-based access control."""
from __future__ import annotations

from functools import wraps

from flask import abort
from flask_login import current_user, login_required

from ..models.user import UserRole


def roles_required(*roles: UserRole):
    """Restrict a view to users whose ``role`` is in ``roles``.

    Usage:
        @roles_required(UserRole.SUPER_ADMIN, UserRole.LOCATION_MANAGER)
        def some_view(): ...
    """
    role_values = {r.value if isinstance(r, UserRole) else r for r in roles}

    def deco(view):
        @wraps(view)
        @login_required
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            role_val = current_user.role.value if hasattr(current_user.role, "value") else current_user.role
            if role_val not in role_values:
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return deco


def admin_required(view):
    return roles_required(UserRole.SUPER_ADMIN, UserRole.LOCATION_MANAGER)(view)


def super_admin_required(view):
    return roles_required(UserRole.SUPER_ADMIN)(view)


def company_admin_required(view):
    return roles_required(UserRole.COMPANY_ADMIN)(view)


def member_required(view):
    return roles_required(UserRole.EMPLOYEE, UserRole.INDIVIDUAL, UserRole.COMPANY_ADMIN)(view)
