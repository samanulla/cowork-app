"""System-wide settings — a single-row table the super admin can edit."""
from __future__ import annotations

from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, Boolean

from ..extensions import db
from ._mixins import TimestampMixin


class SystemSettings(db.Model, TimestampMixin):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True)

    # Locale / currency
    currency_code = Column(String(3), nullable=False, default="INR")
    currency_symbol = Column(String(4), nullable=False, default="₹")
    locale = Column(String(10), nullable=False, default="en_IN")
    number_grouping = Column(String(20), nullable=False, default="indian")  # 'indian' | 'western'

    # Timezone + formats
    timezone = Column(String(64), nullable=False, default="Asia/Kolkata")
    date_format = Column(String(30), nullable=False, default="%d-%b-%Y")
    datetime_format = Column(String(30), nullable=False, default="%d-%b-%Y %H:%M")
    time_format = Column(String(20), nullable=False, default="%H:%M")

    # Tax defaults (GST for India)
    default_tax_rate = Column(Numeric(5, 2), nullable=False, default=Decimal("18.00"))
    tax_label = Column(String(30), nullable=False, default="GST")

    # Business identity (optional — used on invoices/emails)
    company_legal_name = Column(String(200))
    gstin = Column(String(20))
    pan = Column(String(20))
    invoice_prefix = Column(String(10), nullable=False, default="INV")

    # Feature flag
    show_currency_code_after_symbol = Column(Boolean, default=False, nullable=False)

    @classmethod
    def get(cls) -> "SystemSettings":
        """Return the singleton row, creating it with defaults if missing."""
        s = db.session.get(cls, 1)
        if s is None:
            s = cls(id=1)
            db.session.add(s)
            db.session.commit()
        return s
