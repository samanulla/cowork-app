"""Authentication routes."""
from __future__ import annotations

from urllib.parse import urlparse

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, g
from flask_login import login_user, logout_user, login_required, current_user

from ...extensions import db, limiter
from ...models import User, UserRole, Company, CompanyStatus, Tenant
from ...services import mail_service
from .forms import (
    LoginForm, RegisterIndividualForm, RegisterCompanyForm,
    ForgotPasswordForm, ResetPasswordForm, ChangePasswordForm, TenantPickerForm,
)


def _safe_next(target: str | None) -> str | None:
    """Only return the next URL if it's a same-host relative path and not the logout endpoint."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.netloc or parsed.scheme:
        return None
    path = parsed.path or ""
    if not path.startswith("/"):
        return None
    if path.startswith("/auth/logout"):
        return None
    return target


auth_bp = Blueprint("auth", __name__, template_folder="../../templates")


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute; 30 per hour", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("auth.post_login_redirect"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if user and user.check_password(form.password.data) and user.is_active:
            login_user(user, remember=form.remember.data)
            next_url = _safe_next(request.args.get("next"))
            return redirect(next_url or url_for("auth.post_login_redirect"))
        flash("Invalid email or password.", "danger")
    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register_individual():
    if current_user.is_authenticated:
        return redirect(url_for("auth.post_login_redirect"))

    from flask import g
    tenant = getattr(g, "tenant", None)

    form = RegisterIndividualForm()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "warning")
        else:
            user = User(
                tenant_id=tenant.id if tenant else None,
                email=email,
                full_name=form.full_name.data.strip(),
                phone=form.phone.data,
                role=UserRole.INDIVIDUAL,
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash(f"Welcome to {tenant.name if tenant else 'CoWorkHub'}!", "success")
            return redirect(url_for("member.dashboard"))
    return render_template("auth/register_individual.html", form=form)


@auth_bp.route("/register/company", methods=["GET", "POST"])
def register_company():
    if current_user.is_authenticated:
        return redirect(url_for("auth.post_login_redirect"))

    from flask import g
    tenant = getattr(g, "tenant", None)

    form = RegisterCompanyForm()
    if form.validate_on_submit():
        admin_email = form.admin_email.data.lower().strip()
        if User.query.filter_by(email=admin_email).first():
            flash("An account with that admin email already exists.", "warning")
            return render_template("auth/register_company.html", form=form)
        if Company.query.filter_by(name=form.company_name.data.strip()).first():
            flash("A company with that name already exists.", "warning")
            return render_template("auth/register_company.html", form=form)

        company = Company(
            tenant_id=tenant.id if tenant else None,
            name=form.company_name.data.strip(),
            billing_email=form.billing_email.data.lower().strip(),
            status=CompanyStatus.PROSPECT,
        )
        db.session.add(company)
        db.session.flush()

        admin = User(
            tenant_id=tenant.id if tenant else None,
            email=admin_email,
            full_name=form.admin_full_name.data.strip(),
            role=UserRole.COMPANY_ADMIN,
            company_id=company.id,
        )
        admin.set_password(form.password.data)
        db.session.add(admin)
        db.session.commit()

        login_user(admin)
        flash("Your company account is created. A platform admin will contact you to finalise onboarding.", "success")
        return redirect(url_for("company.dashboard"))
    return render_template("auth/register_company.html", form=form)


@auth_bp.route("/post-login")
@login_required
def post_login_redirect():
    """Route logged-in users to their home based on role."""
    role = current_user.role
    if role == UserRole.PLATFORM_OWNER:
        return redirect(url_for("platform.dashboard"))
    if role in (UserRole.SUPER_ADMIN, UserRole.MANAGER, UserRole.LOCATION_MANAGER):
        return redirect(url_for("admin.dashboard"))
    if role == UserRole.COMPANY_ADMIN:
        return redirect(url_for("company.dashboard"))
    return redirect(url_for("member.dashboard"))


PASSWORD_RESET_TTL_SECONDS = 60 * 60 * 2  # 2 hours


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per minute; 20 per hour", methods=["POST"])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        user = User.query.filter_by(email=email).first()
        if user and user.is_active:
            token = mail_service.make_token(user.id, "password-reset")
            reset_url = url_for("auth.reset_password", token=token, _external=True)
            mail_service.send(
                subject="Reset your CoWorkHub password",
                recipient=user.email,
                template="password_reset",
                user=user,
                reset_url=reset_url,
                ttl_hours=PASSWORD_RESET_TTL_SECONDS // 3600,
            )
        flash("If that email is registered here, a reset link has been sent. "
              "Check your inbox (and spam folder).", "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot_password.html", form=form)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    user_id = mail_service.read_token(token, "password-reset", PASSWORD_RESET_TTL_SECONDS)
    if user_id is None:
        flash("This password-reset link is invalid or has expired. Request a new one.", "danger")
        return redirect(url_for("auth.forgot_password"))
    user = User.query.filter_by(id=int(user_id)) \
                     .execution_options(skip_tenant_filter=True).first()
    if user is None or not user.is_active:
        flash("Account not found.", "danger")
        return redirect(url_for("auth.login"))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash("Password updated. Please sign in with your new password.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", form=form)


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("Current password is incorrect.", "danger")
        else:
            current_user.set_password(form.password.data)
            db.session.commit()
            flash("Password changed.", "success")
            return redirect(url_for("auth.post_login_redirect"))
    return render_template("auth/change_password.html", form=form)


@auth_bp.route("/pick-workspace", methods=["GET", "POST"])
def pick_workspace():
    """At the apex domain, let a user type their workspace slug and get redirected."""
    form = TenantPickerForm()
    if form.validate_on_submit():
        slug = form.workspace.data.lower().strip()
        tenant = Tenant.query.filter_by(slug=slug) \
                             .execution_options(skip_tenant_filter=True).first()
        if tenant is None:
            flash(f"No workspace found for '{slug}'. Check the spelling.", "warning")
        else:
            base = current_app.config.get("PLATFORM_BASE_DOMAIN", "coworkhub.io")
            host = tenant.primary_domain or f"{tenant.slug}.{base}"
            scheme = "https" if not current_app.debug else request.scheme
            return redirect(f"{scheme}://{host}/auth/login")
    return render_template("auth/pick_workspace.html", form=form)
