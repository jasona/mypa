from datetime import datetime, timedelta

from app.schemas.email import AgentMailEnvelope
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
