from datetime import datetime, timedelta

import pytest

from app.config import Settings
from app.integrations.calendar import CalendarAPIError, GoogleCalendarService
from app.schemas.calendar import AvailabilityRequest


@pytest.mark.asyncio
async def test_check_availability_supports_multiple_calendar_ids(monkeypatch):
    service = GoogleCalendarService(Settings())

    async def fake_fetch_busy_windows(start_at, end_at, timezone, calendar_ids):
        assert calendar_ids == ["jane@example.com", "john@example.com"]
        return [
            {
                "calendar_id": "jane@example.com",
                "start": datetime(2026, 3, 12, 10, 0, 0),
                "end": datetime(2026, 3, 12, 10, 30, 0),
            }
        ]

    monkeypatch.setattr(service, "_fetch_busy_windows", fake_fetch_busy_windows)

    result = await service.check_availability(
        AvailabilityRequest(
            start_at=datetime(2026, 3, 12, 9, 0, 0),
            end_at=datetime(2026, 3, 12, 11, 0, 0),
            duration_minutes=30,
            timezone="UTC",
            calendar_ids=["jane@example.com", "john@example.com"],
        )
    )

    assert result.queried_calendar_ids == ["jane@example.com", "john@example.com"]
    assert result.busy_windows[0].calendar_id == "jane@example.com"
    assert result.slots[0].start_at.isoformat() == "2026-03-12T09:00:00+00:00"
    assert all(slot.start_at.isoformat() != "2026-03-12T10:00:00+00:00" for slot in result.slots)


def test_resolve_calendar_ids_uses_alias_map():
    settings = Settings(
        CALENDAR_ALIAS_MAP_JSON='{"jane":"jane@example.com","jane smith":"jane.smith@example.com"}'
    )
    service = GoogleCalendarService(settings)

    resolved = service.resolve_calendar_ids(["Jane", "Jane Smith"])

    assert resolved == ["jane@example.com", "jane.smith@example.com"]


def test_resolve_calendar_ids_uses_workspace_domain_fallback():
    settings = Settings(WORKSPACE_EMAIL_DOMAIN="example.com")
    service = GoogleCalendarService(settings)

    resolved = service.resolve_calendar_ids(["Jane Smith", "bob"])

    assert resolved == ["jane.smith@example.com", "bob@example.com"]


def test_resolve_calendar_ids_cleans_email_punctuation():
    service = GoogleCalendarService(Settings())

    resolved = service.resolve_calendar_ids(["jane.smith@example.com?", "<bob@example.com>"])

    assert resolved == ["jane.smith@example.com", "bob@example.com"]


def test_ensure_aware_datetime_uses_request_timezone():
    service = GoogleCalendarService(Settings())
    value = datetime(2026, 3, 12, 9, 0, 0)

    normalized = service._ensure_aware_datetime(value, "America/New_York")

    assert normalized.tzinfo is not None
    assert normalized.isoformat().endswith("-04:00") or normalized.isoformat().endswith("-05:00")


def test_calendar_api_error_exposes_status():
    error = CalendarAPIError(operation="freebusy_query", message="failed", status_code=403)

    assert error.operation == "freebusy_query"
    assert error.status_code == 403
