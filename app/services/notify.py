import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Notification
from app.services.realtime import publish_user

log = logging.getLogger("notify")


def notify(db: Session, user_id: int, title: str, body: str, kind: str = "info") -> None:
    db.add(Notification(user_id=user_id, title=title, body=body, kind=kind))
    db.info.setdefault("after_commit", []).append(
        lambda: publish_user(user_id, {"type": "notification", "title": title, "body": body, "kind": kind})
    )


def send_email(to: str, subject: str, body: str) -> bool:
    """Best-effort SMTP send. Without SMTP_HOST the message is only logged (dev mode)."""
    if not settings.smtp_host:
        log.info("[email disabled] to=%s subject=%s", to, subject)
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.mail_from, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=8) as s:
            s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
        return True
    except Exception:
        log.exception("email send failed")
        return False
