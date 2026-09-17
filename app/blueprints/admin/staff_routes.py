"""Admin routes for staff, salary, and payroll.

Registered onto ``admin_bp`` from ``routes.py`` via ``register_ops_routes``.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user

from ...extensions import db
from ...models import (
    StaffMember, StaffStatus, SalaryStructure,
    PayrollRun, PayrollStatus, Payslip, Location,
)
from ...utils.decorators import admin_required, super_admin_required
from .forms import StaffForm, SalaryStructureForm, PayrollRunForm


def register_staff_routes(bp):

    # ------------------------------------------------------------- staff --
    @bp.route("/staff")
    @admin_required
    def staff_list():
        staff = StaffMember.query.order_by(StaffMember.full_name).all()
        return render_template("admin/staff/list.html", staff=staff)

    @bp.route("/staff/new", methods=["GET", "POST"])
    @admin_required
    def staff_new():
        form = StaffForm()
        form.location_id.choices = [(0, "— unassigned —")] + [
            (l.id, l.name) for l in Location.query.order_by(Location.name).all()
        ]
        if form.validate_on_submit():
            s = StaffMember()
            form.populate_obj(s)
            if s.location_id == 0:
                s.location_id = None
            db.session.add(s)
            db.session.commit()
            flash("Staff member added.", "success")
            return redirect(url_for("admin.staff_detail", staff_id=s.id))
        return render_template("admin/staff/form.html", form=form, title="New staff member")

    @bp.route("/staff/<int:staff_id>")
    @admin_required
    def staff_detail(staff_id: int):
        s = StaffMember.query.get_or_404(staff_id)
        return render_template("admin/staff/detail.html", staff=s)

    @bp.route("/staff/<int:staff_id>/edit", methods=["GET", "POST"])
    @admin_required
    def staff_edit(staff_id: int):
        s = StaffMember.query.get_or_404(staff_id)
        form = StaffForm(obj=s)
        form.location_id.choices = [(0, "— unassigned —")] + [
            (l.id, l.name) for l in Location.query.order_by(Location.name).all()
        ]
        if request.method == "GET" and s.location_id is None:
            form.location_id.data = 0
        if form.validate_on_submit():
            form.populate_obj(s)
            if s.location_id == 0:
                s.location_id = None
            db.session.commit()
            flash("Staff updated.", "success")
            return redirect(url_for("admin.staff_detail", staff_id=s.id))
        return render_template("admin/staff/form.html", form=form, title=f"Edit {s.full_name}")

    @bp.route("/staff/<int:staff_id>/terminate", methods=["POST"])
    @super_admin_required
    def staff_terminate(staff_id: int):
        s = StaffMember.query.get_or_404(staff_id)
        s.status = StaffStatus.TERMINATED
        s.termination_date = date.today()
        # Close open salary structures
        for ss in s.salary_structures:
            if ss.effective_to is None:
                ss.effective_to = date.today()
        db.session.commit()
        flash("Staff member terminated.", "info")
        return redirect(url_for("admin.staff_detail", staff_id=s.id))

    # ---------------------------------------------------------- salary --
    @bp.route("/staff/<int:staff_id>/salary/new", methods=["GET", "POST"])
    @admin_required
    def salary_new(staff_id: int):
        s = StaffMember.query.get_or_404(staff_id)
        form = SalaryStructureForm()
        if form.validate_on_submit():
            # Close existing open structure
            for ss in s.salary_structures:
                if ss.effective_to is None:
                    ss.effective_to = form.effective_from.data
            new_s = SalaryStructure(staff_id=s.id)
            form.populate_obj(new_s)
            db.session.add(new_s)
            db.session.commit()
            flash("Salary structure saved.", "success")
            return redirect(url_for("admin.staff_detail", staff_id=s.id))
        return render_template("admin/staff/salary_form.html", form=form, staff=s)

    # ---------------------------------------------------------- payroll --
    @bp.route("/payroll")
    @admin_required
    def payroll_list():
        runs = PayrollRun.query.order_by(PayrollRun.period_start.desc()).all()
        return render_template("admin/payroll/list.html", runs=runs)

    @bp.route("/payroll/new", methods=["GET", "POST"])
    @super_admin_required
    def payroll_new():
        form = PayrollRunForm()
        if form.validate_on_submit():
            run = PayrollRun(
                period_start=form.period_start.data,
                period_end=form.period_end.data,
                notes=form.notes.data,
                status=PayrollStatus.DRAFT,
                generated_at=datetime.utcnow(),
            )
            db.session.add(run)
            db.session.flush()

            active_staff = StaffMember.query.filter_by(status=StaffStatus.ACTIVE).all()
            total_gross = total_deduct = total_net = Decimal("0")
            for s in active_staff:
                sal = s.current_salary
                if not sal:
                    continue
                p = Payslip(
                    run_id=run.id, staff_id=s.id,
                    basic=sal.basic,
                    allowances=(sal.house_allowance + sal.transport_allowance + sal.other_allowances),
                    deductions=sal.total_deductions,
                    gross=sal.gross, net=sal.net, currency=sal.currency,
                )
                db.session.add(p)
                total_gross += sal.gross
                total_deduct += sal.total_deductions
                total_net += sal.net
            run.total_gross = total_gross
            run.total_deductions = total_deduct
            run.total_net = total_net
            db.session.commit()
            flash(f"Payroll run created with {len(active_staff)} payslip(s).", "success")
            return redirect(url_for("admin.payroll_detail", run_id=run.id))
        return render_template("admin/payroll/form.html", form=form)

    @bp.route("/payroll/<int:run_id>")
    @admin_required
    def payroll_detail(run_id: int):
        run = PayrollRun.query.get_or_404(run_id)
        return render_template("admin/payroll/detail.html", run=run)

    @bp.route("/payroll/<int:run_id>/approve", methods=["POST"])
    @super_admin_required
    def payroll_approve(run_id: int):
        run = PayrollRun.query.get_or_404(run_id)
        run.status = PayrollStatus.APPROVED
        db.session.commit()
        flash("Payroll approved.", "success")
        return redirect(url_for("admin.payroll_detail", run_id=run.id))

    @bp.route("/payroll/<int:run_id>/mark-paid", methods=["POST"])
    @super_admin_required
    def payroll_mark_paid(run_id: int):
        run = PayrollRun.query.get_or_404(run_id)
        run.status = PayrollStatus.PAID
        run.paid_at = datetime.utcnow()
        db.session.commit()
        flash("Payroll marked as paid.", "success")
        return redirect(url_for("admin.payroll_detail", run_id=run.id))
