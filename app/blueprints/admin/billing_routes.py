"""Admin routes for invoicing operations: detail, line items, payments,
credit notes, and refunds."""
from __future__ import annotations

from datetime import datetime, date, timedelta
from decimal import Decimal

from flask import render_template, redirect, url_for, flash
from flask_login import current_user

from ...extensions import db
from ...models import (
    Invoice, InvoiceLineItem, InvoiceStatus, Payment,
    CreditNote, CreditNoteStatus, Refund, RefundStatus,
    Company, User, UserRole,
)
from ...services.billing_service import next_invoice_number
from ...services.formatting import format_money
from ...utils.decorators import admin_required, super_admin_required
from .forms import (
    PaymentForm, InvoiceLineItemForm, CreditNoteForm, RefundForm,
)


def _next_credit_number() -> str:
    ts = datetime.utcnow().strftime("%Y%m")
    last = (CreditNote.query
            .filter(CreditNote.number.like(f"CN-{ts}-%"))
            .order_by(CreditNote.id.desc()).first())
    seq = 1 if last is None else int(last.number.split("-")[-1]) + 1
    return f"CN-{ts}-{seq:05d}"


def _recompute_invoice(inv: Invoice) -> None:
    subtotal = sum((Decimal(li.amount or 0) for li in inv.line_items), Decimal("0"))
    inv.subtotal = subtotal
    inv.total_amount = subtotal + Decimal(inv.tax_amount or 0)


def _refresh_invoice_status(inv: Invoice) -> None:
    balance = Decimal(inv.total_amount or 0) - Decimal(inv.amount_paid or 0)
    if balance <= 0:
        inv.status = InvoiceStatus.PAID
    elif inv.amount_paid and inv.amount_paid > 0:
        inv.status = InvoiceStatus.PARTIAL
    elif inv.due_date and inv.due_date < date.today():
        inv.status = InvoiceStatus.OVERDUE


def register_billing_routes(bp):

    # ---------------------------------------------------------- invoices --
    @bp.route("/invoices/new", methods=["GET", "POST"])
    @admin_required
    def invoice_new():
        from flask import request
        # Simple ad-hoc invoice creation
        if request.method == "POST":
            company_id = request.form.get("company_id", type=int) or None
            user_id = request.form.get("user_id", type=int) or None
            if not company_id and not user_id:
                flash("Choose a company or an individual.", "warning")
            else:
                today = date.today()
                inv = Invoice(
                    number=next_invoice_number(),
                    company_id=company_id, user_id=user_id,
                    period_start=today, period_end=today,
                    due_date=today + timedelta(days=15),
                    status=InvoiceStatus.DRAFT,
                    subtotal=0, total_amount=0,
                )
                db.session.add(inv)
                db.session.commit()
                return redirect(url_for("admin.invoice_detail", invoice_id=inv.id))
        companies = Company.query.order_by(Company.name).all()
        users = User.query.filter_by(role=UserRole.INDIVIDUAL).order_by(User.full_name).all()
        return render_template("admin/invoices/new.html", companies=companies, users=users)

    @bp.route("/invoices/<int:invoice_id>", methods=["GET", "POST"])
    @admin_required
    def invoice_detail(invoice_id: int):
        inv = Invoice.query.get_or_404(invoice_id)
        line_form = InvoiceLineItemForm()
        payment_form = PaymentForm()
        payment_form.paid_at.data = date.today()

        # Credit notes issued against this invoice
        credit_notes = (CreditNote.query.filter_by(invoice_id=inv.id)
                        .order_by(CreditNote.created_at.desc()).all())
        return render_template("admin/invoices/detail.html",
                               invoice=inv,
                               line_form=line_form,
                               payment_form=payment_form,
                               credit_notes=credit_notes)

    @bp.route("/invoices/<int:invoice_id>/lines/add", methods=["POST"])
    @admin_required
    def invoice_line_add(invoice_id: int):
        inv = Invoice.query.get_or_404(invoice_id)
        if inv.status not in (InvoiceStatus.DRAFT, InvoiceStatus.ISSUED):
            flash("Only draft/issued invoices can be edited.", "warning")
            return redirect(url_for("admin.invoice_detail", invoice_id=inv.id))

        form = InvoiceLineItemForm()
        if form.validate_on_submit():
            line = InvoiceLineItem(
                invoice_id=inv.id,
                description=form.description.data,
                quantity=form.quantity.data,
                unit_price=form.unit_price.data,
                amount=(Decimal(form.quantity.data) * Decimal(form.unit_price.data)).quantize(Decimal("0.01")),
            )
            db.session.add(line)
            db.session.flush()
            _recompute_invoice(inv)
            db.session.commit()
            flash("Line item added.", "success")
        else:
            flash("Invalid line item.", "danger")
        return redirect(url_for("admin.invoice_detail", invoice_id=inv.id))

    @bp.route("/invoices/<int:invoice_id>/lines/<int:line_id>/delete", methods=["POST"])
    @admin_required
    def invoice_line_delete(invoice_id: int, line_id: int):
        inv = Invoice.query.get_or_404(invoice_id)
        line = InvoiceLineItem.query.get_or_404(line_id)
        db.session.delete(line)
        db.session.flush()
        _recompute_invoice(inv)
        db.session.commit()
        flash("Line removed.", "info")
        return redirect(url_for("admin.invoice_detail", invoice_id=inv.id))

    @bp.route("/invoices/<int:invoice_id>/issue", methods=["POST"])
    @admin_required
    def invoice_issue(invoice_id: int):
        inv = Invoice.query.get_or_404(invoice_id)
        inv.status = InvoiceStatus.ISSUED
        inv.issued_at = datetime.utcnow()
        db.session.commit()
        flash("Invoice issued.", "success")
        return redirect(url_for("admin.invoice_detail", invoice_id=inv.id))

    @bp.route("/invoices/<int:invoice_id>/void", methods=["POST"])
    @super_admin_required
    def invoice_void(invoice_id: int):
        inv = Invoice.query.get_or_404(invoice_id)
        inv.status = InvoiceStatus.VOID
        db.session.commit()
        flash("Invoice voided.", "info")
        return redirect(url_for("admin.invoice_detail", invoice_id=inv.id))

    # ----------------------------------------------------------- payments --
    @bp.route("/invoices/<int:invoice_id>/payments/new", methods=["POST"])
    @admin_required
    def payment_new(invoice_id: int):
        inv = Invoice.query.get_or_404(invoice_id)
        form = PaymentForm()
        if not form.validate_on_submit():
            flash("Invalid payment.", "danger")
            return redirect(url_for("admin.invoice_detail", invoice_id=inv.id))
        p = Payment(
            invoice_id=inv.id,
            amount=form.amount.data,
            method=form.method.data,
            reference=form.reference.data,
            paid_at=datetime.combine(form.paid_at.data, datetime.min.time()),
        )
        db.session.add(p)
        inv.amount_paid = Decimal(inv.amount_paid or 0) + Decimal(form.amount.data)
        _refresh_invoice_status(inv)
        db.session.commit()
        flash(f"Recorded {format_money(form.amount.data)} payment.", "success")
        return redirect(url_for("admin.invoice_detail", invoice_id=inv.id))

    # ----------------------------------------------------- credit notes --
    @bp.route("/credit-notes")
    @admin_required
    def credit_notes():
        notes = CreditNote.query.order_by(CreditNote.created_at.desc()).all()
        return render_template("admin/finance/credit_notes.html", notes=notes)

    @bp.route("/credit-notes/new", methods=["GET", "POST"])
    @admin_required
    def credit_note_new():
        form = CreditNoteForm()
        form.company_id.choices = [(0, "— none —")] + [
            (c.id, c.name) for c in Company.query.order_by(Company.name).all()
        ]
        form.user_id.choices = [(0, "— none —")] + [
            (u.id, f"{u.full_name} ({u.email})")
            for u in User.query.filter_by(role=UserRole.INDIVIDUAL).order_by(User.full_name).all()
        ]
        form.invoice_id.choices = [(0, "— none —")] + [
            (i.id, f"{i.number} ({format_money(i.total_amount)})")
            for i in Invoice.query.order_by(Invoice.id.desc()).limit(200).all()
        ]
        if form.validate_on_submit():
            if not form.company_id.data and not form.user_id.data:
                flash("Choose a company or an individual.", "warning")
                return render_template("admin/finance/credit_note_form.html", form=form)
            cn = CreditNote(
                number=_next_credit_number(),
                company_id=form.company_id.data or None,
                user_id=form.user_id.data or None,
                invoice_id=form.invoice_id.data or None,
                amount=form.amount.data,
                currency=form.currency.data,
                reason=form.reason.data,
                notes=form.notes.data,
                status=CreditNoteStatus.ISSUED,
                issued_by_id=current_user.id,
                issued_at=datetime.utcnow(),
            )
            db.session.add(cn)
            db.session.commit()
            flash(f"Credit note {cn.number} issued.", "success")
            return redirect(url_for("admin.credit_notes"))
        return render_template("admin/finance/credit_note_form.html", form=form)

    @bp.route("/credit-notes/<int:cn_id>/apply", methods=["POST"])
    @admin_required
    def credit_note_apply(cn_id: int):
        cn = CreditNote.query.get_or_404(cn_id)
        if cn.status != CreditNoteStatus.ISSUED:
            flash("Only issued credit notes can be applied.", "warning")
            return redirect(url_for("admin.credit_notes"))
        if cn.invoice_id:
            inv = Invoice.query.get(cn.invoice_id)
            if inv:
                inv.amount_paid = Decimal(inv.amount_paid or 0) + Decimal(cn.amount or 0)
                _refresh_invoice_status(inv)
        cn.status = CreditNoteStatus.APPLIED
        cn.applied_at = datetime.utcnow()
        db.session.commit()
        flash(f"Credit note {cn.number} applied.", "success")
        return redirect(url_for("admin.credit_notes"))

    @bp.route("/credit-notes/<int:cn_id>/cancel", methods=["POST"])
    @super_admin_required
    def credit_note_cancel(cn_id: int):
        cn = CreditNote.query.get_or_404(cn_id)
        cn.status = CreditNoteStatus.CANCELLED
        db.session.commit()
        flash("Credit note cancelled.", "info")
        return redirect(url_for("admin.credit_notes"))

    # --------------------------------------------------------- refunds --
    @bp.route("/refunds")
    @admin_required
    def refunds():
        refs = Refund.query.order_by(Refund.created_at.desc()).all()
        return render_template("admin/finance/refunds.html", refunds=refs)

    @bp.route("/payments/<int:payment_id>/refund", methods=["GET", "POST"])
    @admin_required
    def refund_new(payment_id: int):
        p = Payment.query.get_or_404(payment_id)
        form = RefundForm()
        form.amount.data = form.amount.data or p.amount
        if form.validate_on_submit():
            if Decimal(form.amount.data) > Decimal(p.amount or 0):
                flash("Refund amount cannot exceed payment amount.", "warning")
            else:
                r = Refund(
                    payment_id=p.id,
                    amount=form.amount.data,
                    reason=form.reason.data,
                    method=form.method.data,
                    reference=form.reference.data,
                    notes=form.notes.data,
                    status=RefundStatus.PENDING,
                )
                db.session.add(r)
                # Reflect on invoice balance
                inv = p.invoice
                if inv:
                    inv.amount_paid = max(Decimal(0), Decimal(inv.amount_paid or 0) - Decimal(form.amount.data))
                    _refresh_invoice_status(inv)
                db.session.commit()
                flash(f"Refund of {format_money(form.amount.data)} recorded (pending).", "success")
                return redirect(url_for("admin.refunds"))
        return render_template("admin/finance/refund_form.html", form=form, payment=p)

    @bp.route("/refunds/<int:refund_id>/complete", methods=["POST"])
    @super_admin_required
    def refund_complete(refund_id: int):
        r = Refund.query.get_or_404(refund_id)
        r.status = RefundStatus.COMPLETED
        r.processed_at = datetime.utcnow()
        r.processed_by_id = current_user.id
        db.session.commit()
        flash("Refund marked complete.", "success")
        return redirect(url_for("admin.refunds"))

    @bp.route("/refunds/<int:refund_id>/fail", methods=["POST"])
    @super_admin_required
    def refund_fail(refund_id: int):
        r = Refund.query.get_or_404(refund_id)
        r.status = RefundStatus.FAILED
        r.processed_at = datetime.utcnow()
        r.processed_by_id = current_user.id
        db.session.commit()
        flash("Refund marked failed.", "info")
        return redirect(url_for("admin.refunds"))
