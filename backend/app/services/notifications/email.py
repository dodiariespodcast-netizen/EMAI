"""Outbound email. Falls back to logging the message when SMTP isn't
configured, so the product works in trial/dev without an email provider
wired up -- same graceful-degradation pattern as the AI client.

Kept deliberately synchronous and dependency-free (stdlib smtplib): the
volume here (a handful of transactional emails per schedule run or
request) never needs a queue, and callers already run inside FastAPI's
threadpool for sync endpoints.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger("emai.notifications")


def send_email(to: str, subject: str, body: str) -> bool:
    """Returns True if the message was handed off to an SMTP server, False
    if it was only logged (no SMTP configured) or delivery failed. Never
    raises -- a notification failure should never fail the API request that
    triggered it."""
    settings = get_settings()
    if not settings.smtp_host:
        logger.info("EMAIL (no SMTP configured) to=%s subject=%r\n%s", to, subject, body)
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{settings.email_from_name} <{settings.email_from_address}>"
    message["To"] = to
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username and settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False
