from datetime import datetime, timezone
from sqlalchemy import select
from models import TaskAssignment, EmailNotification
from services.email_service import send_email

def reminder_candidates(db, now=None):
    # Simple MVP hook: reminders can be triggered manually from the admin dashboard.
    # For reliable production scheduling, use a persistent worker/queue.
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    return db.scalars(select(TaskAssignment).where(
        TaskAssignment.status.in_(["ASSIGNED", "IN_PROGRESS", "SUBMITTED", "REVISION_REQUIRED"])
    )).all()

def notify(db, recipient, subject, body):
    status, error = send_email(recipient, subject, body)
    record = EmailNotification(recipient=recipient, subject=subject, body=body, status=status, error=error)
    db.add(record)
    db.commit()
    return status, error
