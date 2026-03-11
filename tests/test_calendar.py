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
    assert result.slots[0].start_at == datetime(2026, 3, 12, 9, 0, 0)
    assert all(slot.start_at != datetime(2026, 3, 12, 10, 0, 0) for slot in result.slots)


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


def test_calendar_api_error_exposes_status():
    error = CalendarAPIError(operation="freebusy_query", message="failed", status_code=403)

    assert error.operation == "freebusy_query"
    assert error.status_code == 403
