from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from google.auth.transport.requests import Request
from google.auth.exceptions import GoogleAuthError
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config import (
    GOOGLE_CALENDAR_ID,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_MEET_DURATION_MINUTES,
    GOOGLE_REFRESH_TOKEN,
)


def calendar_is_configured():
    return all([GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN])


def validate_review_slot(review_datetime, timezone_name):
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown IANA time zone: {timezone_name}") from exc
    try:
        local_start = datetime.fromisoformat(review_datetime)
    except ValueError as exc:
        raise ValueError("Review date/time must use YYYY-MM-DD HH:MM format.") from exc
    if local_start.tzinfo is not None:
        raise ValueError("Review date/time should be local time; provide its IANA time zone separately.")
    start = local_start.replace(tzinfo=zone)
    if start <= datetime.now(zone):
        raise ValueError("Review date/time must be in the future.")
    if not 5 <= GOOGLE_MEET_DURATION_MINUTES <= 240:
        raise ValueError("GOOGLE_MEET_DURATION_MINUTES must be between 5 and 240.")
    return start, start + timedelta(minutes=GOOGLE_MEET_DURATION_MINUTES)


def create_review_meeting(
    *,
    attendee_email,
    task_title,
    review_datetime,
    timezone_name,
):
    if not calendar_is_configured():
        raise RuntimeError(
            "Google Calendar is not configured. Set GOOGLE_CLIENT_ID, "
            "GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN in .env."
        )
    start, end = validate_review_slot(review_datetime, timezone_name)
    credentials = Credentials(
        token=None,
        refresh_token=GOOGLE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/calendar.events"],
    )
    try:
        credentials.refresh(Request())
        calendar = build("calendar", "v3", credentials=credentials, cache_discovery=False)
        event = calendar.events().insert(
            calendarId=GOOGLE_CALENDAR_ID,
            conferenceDataVersion=1,
            sendUpdates="all",
            body={
                "summary": f"Intern review: {task_title}",
                "description": f"Review meeting for internship task: {task_title}",
                "start": {
                    "dateTime": start.isoformat(),
                    "timeZone": timezone_name,
                },
                "end": {
                    "dateTime": end.isoformat(),
                    "timeZone": timezone_name,
                },
                "attendees": [{"email": attendee_email}],
                "conferenceData": {
                    "createRequest": {
                        "requestId": uuid4().hex,
                        "conferenceSolutionKey": {"type": "hangoutsMeet"},
                    }
                },
            },
        ).execute()
    except GoogleAuthError as exc:
        raise RuntimeError(
            "Google Calendar authorization failed. Check the OAuth client, refresh token, "
            "and Calendar events scope."
        ) from exc
    except HttpError as exc:
        raise RuntimeError(
            f"Google Calendar request failed (HTTP {exc.resp.status}). "
            "Check that Calendar API is enabled and the calendar is writable."
        ) from exc
    meet_url = event.get("hangoutLink")
    if not meet_url:
        conference = event.get("conferenceData", {})
        meet_url = next(
            (
                entry.get("uri")
                for entry in conference.get("entryPoints", [])
                if entry.get("entryPointType") == "video" and entry.get("uri")
            ),
            None,
        )
    if not meet_url:
        if event.get("id"):
            delete_review_meeting(event["id"])
        raise RuntimeError(
            "Google Calendar created the review event but did not return a Meet link. "
            f"Event ID: {event.get('id', 'unknown')}."
        )
    return {"meet_url": meet_url, "event_id": event.get("id")}


def delete_review_meeting(event_id):
    credentials = Credentials(
        token=None,
        refresh_token=GOOGLE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/calendar.events"],
    )
    try:
        credentials.refresh(Request())
        calendar = build("calendar", "v3", credentials=credentials, cache_discovery=False)
        calendar.events().delete(
            calendarId=GOOGLE_CALENDAR_ID,
            eventId=event_id,
            sendUpdates="all",
        ).execute()
    except (GoogleAuthError, HttpError) as exc:
        raise RuntimeError(
            "Could not cancel a review event created during a failed cohort import."
        ) from exc
