from datetime import datetime, timedelta

import pytest

from app.schemas.email import AgentMailEnvelope
from app.integrations.calendar import CalendarAPIError
from app.services.scheduler import SchedulerService


def test_select_candidate_slots_respects_spacing():
    base = datetime(2026, 3, 10, 13, 0, 0)
    slots = [
        {"start_at": base.isoformat(), "end_at": (base + timedelta(minutes=30)).isoformat()},
        {
            "start_at": (base + timedelta(minutes=30)).isoformat(),
            "end_at": (base + timedelta(minutes=60)).isoformat(),
        },
        {
            "start_at": (base + timedelta(minutes=90)).isoformat(),
            "end_at": (base + timedelta(minutes=120)).isoformat(),
        },
    ]

    selected = SchedulerService.select_candidate_slots(slots, count=3, min_spacing_minutes=60)

    assert len(selected) == 2
    assert selected[0]["start_at"] == base.isoformat()
    assert selected[1]["start_at"] == (base + timedelta(minutes=90)).isoformat()


def test_summarize_email_trims_signature_content():
    received_at = datetime(2026, 3, 10, 13, 0, 0)
    envelope = AgentMailEnvelope(
        event_id="evt-1",
        event_type="message.received",
        inbox_id="inbox-1",
        thread_id="thread-1",
        message_id="msg-1",
        subject="Test",
        sender="sender@example.com",
        preview="This is a test. Can you reply yet?\n\nBest,\nJason",
        body_text="",
        received_at=received_at,
    )

    summary = SchedulerService.summarize_email(envelope)

    assert summary == "This is a test. Can you reply yet?"


@pytest.mark.asyncio
async def test_handle_telegram_message_returns_friendly_calendar_error():
    scheduler = SchedulerService.__new__(SchedulerService)
    scheduler.settings = type("SettingsStub", (), {"app_timezone": "UTC"})()

    class CalendarStub:
        async def upcoming_context(self, days=14):
            return []

    class AgentStub:
        async def run(self, **kwargs):
            raise CalendarAPIError(operation="freebusy_query", message="failed", status_code=403)

    scheduler.calendar = CalendarStub()
    scheduler.agent = AgentStub()
    scheduler._tool_handlers = lambda **kwargs: {}

    from app.schemas.telegram import TelegramInboundMessage

    reply = await scheduler.handle_telegram_message(
        TelegramInboundMessage(
            chat_id="123",
            text="What is Jane's schedule today?",
            message_id="1",
            sent_at=datetime(2026, 3, 10, 12, 0, 0),
        )
    )

    assert "I couldn't check that calendar right now." in reply
