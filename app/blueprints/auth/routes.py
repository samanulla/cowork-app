"""Authentication routes."""
from __future__ import annotations

from urllib.parse import urlparse

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from ...extensions import db, limiter
from ...models import User, UserRole, Company, CompanyStatus
from .forms import LoginForm, RegisterIndividualForm, RegisterCompanyForm


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

    form = RegisterIndividualForm()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "warning")
        else:
            user = User(
                email=email,
                full_name=form.full_name.data.strip(),
                phone=form.phone.data,
                role=UserRole.INDIVIDUAL,
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Welcome to CoWorkHub!", "success")
            return redirect(url_for("member.dashboard"))
    return render_template("auth/register_individual.html", form=form)


@auth_bp.route("/register/company", methods=["GET", "POST"])
def register_company():
    if current_user.is_authenticated:
        return redirect(url_for("auth.post_login_redirect"))

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
            name=form.company_name.data.strip(),
            billing_email=form.billing_email.data.lower().strip(),
            status=CompanyStatus.PROSPECT,
        )
        db.session.add(company)
        db.session.flush()

        admin = User(
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
    if role in (UserRole.SUPER_ADMIN, UserRole.MANAGER, UserRole.LOCATION_MANAGER):
        return redirect(url_for("admin.dashboard"))
    if role == UserRole.COMPANY_ADMIN:
        return redirect(url_for("company.dashboard"))
    return redirect(url_for("member.dashboard"))
