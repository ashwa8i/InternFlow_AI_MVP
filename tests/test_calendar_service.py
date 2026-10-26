from datetime import datetime, timedelta

import pytest

from services import calendar_service


def test_review_slot_preserves_timezone_and_duration(monkeypatch):
    monkeypatch.setattr(calendar_service, "GOOGLE_MEET_DURATION_MINUTES", 30)
    local_start = (datetime.now() + timedelta(days=2)).replace(
        hour=14, minute=0, second=0, microsecond=0
    )

    start, end = calendar_service.validate_review_slot(
        local_start.strftime("%Y-%m-%d %H:%M"),
        "Asia/Kolkata",
    )

    assert start.tzinfo is not None
    assert start.strftime("%z") == "+0530"
    assert end - start == timedelta(minutes=30)


def test_review_slot_rejects_past_time():
    with pytest.raises(ValueError, match="must be in the future"):
        calendar_service.validate_review_slot(
            "2000-01-01 12:00",
            "Asia/Kolkata",
        )


def test_review_slot_rejects_unknown_timezone():
    future = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d %H:%M")
    with pytest.raises(ValueError, match="Unknown IANA time zone"):
        calendar_service.validate_review_slot(future, "Not/A_Timezone")


def test_create_review_meeting_requests_calendar_meet(monkeypatch):
    event_body = {}
    request_options = {}

    class FakeCredentials:
        def __init__(self, **_kwargs):
            pass

        def refresh(self, _request):
            pass

    class FakeEvents:
        def insert(self, **kwargs):
            event_body.update(kwargs["body"])
            request_options.update(
                conferenceDataVersion=kwargs["conferenceDataVersion"],
                sendUpdates=kwargs["sendUpdates"],
            )

            class Result:
                def execute(self):
                    return {"id": "event-1", "hangoutLink": "https://meet.google.test/event-1"}

            return Result()

    class FakeCalendar:
        def events(self):
            return FakeEvents()

    monkeypatch.setattr(calendar_service, "GOOGLE_CLIENT_ID", "client")
    monkeypatch.setattr(calendar_service, "GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setattr(calendar_service, "GOOGLE_REFRESH_TOKEN", "refresh")
    monkeypatch.setattr(calendar_service, "GOOGLE_MEET_DURATION_MINUTES", 30)
    monkeypatch.setattr(calendar_service, "Credentials", FakeCredentials)
    monkeypatch.setattr(calendar_service, "Request", lambda: object())
    monkeypatch.setattr(calendar_service, "build", lambda *_args, **_kwargs: FakeCalendar())

    review_time = (datetime.now() + timedelta(days=2)).replace(
        hour=14, minute=0, second=0, microsecond=0
    ).strftime("%Y-%m-%d %H:%M")
    result = calendar_service.create_review_meeting(
        attendee_email="intern@example.test",
        task_title="Build a portfolio",
        review_datetime=review_time,
        timezone_name="Asia/Kolkata",
    )

    assert result == {
        "meet_url": "https://meet.google.test/event-1",
        "event_id": "event-1",
    }
    assert event_body["attendees"] == [{"email": "intern@example.test"}]
    assert event_body["conferenceData"]["createRequest"]["conferenceSolutionKey"]["type"] == "hangoutsMeet"
    assert request_options == {"conferenceDataVersion": 1, "sendUpdates": "all"}
