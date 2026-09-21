from __future__ import annotations

import os
import re
import smtplib
from email.message import EmailMessage

from ..util.logging import setup_logger

logger, _ = setup_logger()


def send_digest_email(html: str, *, subject: str, text_fallback: str = "") -> None:
    """Send HTML digest via Gmail SMTP-SSL (needs an App Password)."""
    sender = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    # GMAIL_TO may hold several addresses separated by commas / semicolons / whitespace
    recipients = [r for r in re.split(r"[,;\s]+", os.environ.get("GMAIL_TO", sender)) if r]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(text_fallback or "Your email client does not support HTML.")
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)

    logger.info(f"Email → {', '.join(recipients)}")
