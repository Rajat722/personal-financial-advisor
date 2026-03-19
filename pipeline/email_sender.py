# pipeline/email_sender.py
"""Gmail SMTP email delivery for Portfolio Pulse digests.

Uses Gmail's SMTP server with an App Password (requires 2FA on the Gmail account).
Failures are logged but never raised — a send error never aborts the pipeline.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from core.config import settings
from core.logging import get_logger

logger = get_logger("email_sender")

GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587


def send_digest(
    *,
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
) -> bool:
    """Send an HTML digest email via Gmail SMTP.

    Returns True on success, False on any failure.
    Logs errors but never raises — caller treats False as a soft failure.
    """
    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        logger.warning("GMAIL_USER or GMAIL_APP_PASSWORD not set — skipping email send.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Portfolio Pulse <{settings.GMAIL_USER}>"
    msg["To"] = f"{to_name} <{to_email}>"
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(settings.GMAIL_USER, settings.GMAIL_APP_PASSWORD)
            smtp.sendmail(settings.GMAIL_USER, to_email, msg.as_string())
        logger.info(f"Email sent to {to_email}.")
        return True
    except Exception as e:
        logger.error(f"Email send failed for {to_email}: {e}")
        return False