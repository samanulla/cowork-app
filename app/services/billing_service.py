"""Billing service — invoice number generation and monthly billing runs (skeleton)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from ..extensions import db
from ..models import (
    Invoice, InvoiceLineItem, InvoiceStatus, Subscription, SubscriptionStatus,
    SystemSettings,
)


def _prefix() -> str:
    try:
        return (SystemSettings.get().invoice_prefix or "INV").strip() or "INV"
    except Exception:
        return "INV"


def next_invoice_number() -> str:
    prefix = _prefix()
    ts = datetime.utcnow().strftime("%Y%m")
    last = (Invoice.query
            .filter(Invoice.number.like(f"{prefix}-{ts}-%"))
            .order_by(Invoice.id.desc())
            .first())
    seq = 1 if last is None else int(last.number.split("-")[-1]) + 1
    return f"{prefix}-{ts}-{seq:05d}"


def _default_tax_rate() -> Decimal:
    try:
        rate = SystemSettings.get().default_tax_rate
        return (Decimal(rate) / Decimal(100)) if rate is not None else Decimal("0")
    except Exception:
        return Decimal("0")


def generate_invoice_for_subscription(sub: Subscription,
                                      period_start: date, period_end: date,
                                      tax_rate: Decimal | None = None) -> Invoice:
    if tax_rate is None:
        tax_rate = _default_tax_rate()
    subtotal = Decimal(sub.unit_price or 0) * Decimal(sub.quantity or 1)
    tax = (subtotal * tax_rate).quantize(Decimal("0.01"))
    total = subtotal + tax

    inv = Invoice(
        number=next_invoice_number(),
        company_id=sub.company_id,
        user_id=sub.user_id,
        period_start=period_start,
        period_end=period_end,
        issued_at=datetime.utcnow(),
        due_date=period_end + timedelta(days=15),
        subtotal=subtotal,
        tax_amount=tax,
        total_amount=total,
        status=InvoiceStatus.ISSUED,
    )
    db.session.add(inv)
    db.session.flush()

    db.session.add(InvoiceLineItem(
        invoice_id=inv.id,
        description=f"{sub.plan.name} × {sub.quantity} ({period_start} to {period_end})",
        quantity=Decimal(sub.quantity or 1),
        unit_price=Decimal(sub.unit_price or 0),
        amount=subtotal,
    ))
    db.session.commit()
    return inv


def run_monthly_billing(target_month: date | None = None) -> list[Invoice]:
    """Generate invoices for every ACTIVE subscription for the given month.
    In production, run this from a scheduled task (EventBridge / Azure Scheduler)."""
    if target_month is None:
        target_month = date.today().replace(day=1)

    period_start = target_month.replace(day=1)
    if period_start.month == 12:
        period_end = period_start.replace(year=period_start.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        period_end = period_start.replace(month=period_start.month + 1, day=1) - timedelta(days=1)

    active = Subscription.query.filter(Subscription.status == SubscriptionStatus.ACTIVE).all()
    return [generate_invoice_for_subscription(sub, period_start, period_end) for sub in active]
