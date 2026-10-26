import smtplib
from email.message import EmailMessage
from config import DEMO_MODE, SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL, SMTP_USE_TLS

def send_email(recipient: str, subject: str, body: str) -> tuple[str, str]:
    """Returns (status, error). SMTP acceptance is not proof of inbox delivery."""
    if DEMO_MODE or not all([SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL]):
        return "SIMULATED", "Demo mode or SMTP credentials not configured; no real email sent."
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM_EMAIL
    msg["To"] = recipient
    msg.set_content(body)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            if SMTP_USE_TLS:
                server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        return "SMTP_ACCEPTED", "Accepted by SMTP server; inbox delivery is not guaranteed."
    except Exception as exc:
        return "FAILED", str(exc)[:1000]

def task_email(intern_name, task_title, description, deadline, review_at, meet_url, app_url="local Streamlit dashboard"):
    body = f"""Hello {intern_name},

A task has been assigned to you.

Task: {task_title}

Instructions:
{description}

Deadline: {deadline}
Review: {review_at or 'To be confirmed'}
Google Meet: {meet_url or 'To be provided by your mentor'}

Submission: Open your InternFlow dashboard and submit a GitHub or Google Drive link.
Dashboard: {app_url}

If you have a doubt, use the AI assistant in the dashboard and include the task title.

Regards,
InternFlow AI Internship Coordinator
"""
    return body
