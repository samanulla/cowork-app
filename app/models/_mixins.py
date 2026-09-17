"""Shared model mixins."""
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer


class TimestampMixin:
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class PkMixin:
    id = Column(Integer, primary_key=True)
