"""Email sending + secure signed tokens for password reset / invitations.

Uses Flask-Mail (SMTP) — works with local dev, SES SMTP, SendGrid, etc.
No separate DB table needed: tokens are self-contained + expiry-signed via itsdangerous.
"""
from __future__ import annotations

from typing import Any

from flask import current_app, render_template
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from ..extensions import mail


def _serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=salt)


def make_token(payload: Any, purpose: str) -> str:
    return _serializer(f"cowork-{purpose}").dumps(payload)


def read_token(token: str, purpose: str, max_age_seconds: int) -> Any | None:
    try:
        return _serializer(f"cowork-{purpose}").loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None


def send(subject: str, recipient: str, template: str, **ctx: Any) -> None:
    """Render ``templates/emails/<template>.txt`` and .html and send via SMTP.

    Falls back to logging when MAIL_SUPPRESS_SEND is true (tests / dev).
    """
    body_txt = render_template(f"emails/{template}.txt", **ctx)
    try:
        body_html = render_template(f"emails/{template}.html", **ctx)
    except Exception:
        body_html = None
    msg = Message(subject=subject, recipients=[recipient],
                  body=body_txt, html=body_html)
    if current_app.config.get("MAIL_SUPPRESS_SEND"):
        current_app.logger.info("MAIL SUPPRESSED to=%s subject=%s\n%s",
                                recipient, subject, body_txt)
        return
    mail.send(msg)
