from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Any

from job_assistant.config import settings

logger = logging.getLogger(__name__)

DEV_EMAIL_OUTBOX: list[dict[str, Any]] = []


def send_password_reset_email(email: str, reset_url: str) -> None:
    """Send a password reset link without leaking raw tokens in production logs."""
    if settings.smtp_host and settings.smtp_from_email:
        message = EmailMessage()
        message["Subject"] = "Reset your Job Assistant password"
        message["From"] = settings.smtp_from_email
        message["To"] = email
        message.set_content(
            "Use this link to reset your password. "
            f"The link expires in {settings.password_reset_token_expire_minutes} minutes.\n\n{reset_url}\n\n"
            "If you did not request this, you can ignore this email."
        )
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
        return

    if settings.is_production:
        raise RuntimeError("SMTP is not configured for password recovery.")

    DEV_EMAIL_OUTBOX.append({"to": email, "reset_url": reset_url})
    logger.info("Password reset email captured for %s in development outbox.", email)
