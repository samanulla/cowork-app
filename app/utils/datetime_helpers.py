"""Datetime helpers."""
from __future__ import annotations

from datetime import datetime


def parse_dt_local(value: str) -> datetime:
    """Parse an HTML <input type=datetime-local> value (e.g. '2026-01-15T09:30')."""
    return datetime.strptime(value, "%Y-%m-%dT%H:%M")
