from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import ThreadStatus
from app.schemas.email import AgentMailEnvelope
from app.integrations.calendar import CalendarAPIError
from app.services.scheduler import SchedulerService


async def _async_return(value):
    return value


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


def test_prepare_email_body_for_llm_strips_quoted_history_and_truncates():
    scheduler = SchedulerService.__new__(SchedulerService)
    scheduler.settings = type("SettingsStub", (), {"max_email_body_chars": 40})()
    envelope = AgentMailEnvelope(
        event_id="evt-1",
        event_type="message.received",
        inbox_id="inbox-1",
        thread_id="thread-1",
        message_id="msg-1",
        subject="Test",
        sender="sender@example.com",
        preview="",
        body_text="Hello team,\nCan we meet tomorrow?\n\nOn Tue, someone wrote:\n> quoted history",
        received_at=datetime(2026, 3, 10, 13, 0, 0),
    )

    excerpt = scheduler.prepare_email_body_for_llm(envelope)

    assert "quoted history" not in excerpt
    assert "On Tue, someone wrote:" not in excerpt
    assert excerpt == "Hello team,\nCan we meet tomorrow?"


def test_filter_upcoming_events_for_thread_returns_summarized_bound_events():
    events = [
        {"id": "evt-1", "summary": "One", "status": "confirmed", "start": {"dateTime": "a"}, "end": {"dateTime": "b"}},
        {"id": "evt-2", "summary": "Two", "status": "tentative", "start": {"dateTime": "c"}, "end": {"dateTime": "d"}},
    ]

    filtered = SchedulerService._filter_upcoming_events_for_thread(events, {"evt-2"})

    assert filtered == [
        {"id": "evt-2", "summary": "Two", "status": "tentative", "start": {"dateTime": "c"}, "end": {"dateTime": "d"}}
    ]


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


@pytest.mark.asyncio
async def test_handle_telegram_message_includes_google_error_message():
    scheduler = SchedulerService.__new__(SchedulerService)
    scheduler.settings = type("SettingsStub", (), {"app_timezone": "UTC"})()

    class CalendarStub:
        async def upcoming_context(self, days=14):
            return []

    class AgentStub:
        async def run(self, **kwargs):
            raise CalendarAPIError(
                operation="freebusy_query",
                message="failed",
                status_code=400,
                response_text="Invalid calendar identifier",
            )

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

    assert "Google returned 400." in reply
    assert "Invalid calendar identifier" in reply


@pytest.mark.asyncio
async def test_handle_telegram_message_passes_local_date_context():
    captured: dict = {}
    scheduler = SchedulerService.__new__(SchedulerService)
    scheduler.settings = type(
        "SettingsStub",
        (),
        {
            "app_timezone": "America/New_York",
            "timezone": __import__("zoneinfo").ZoneInfo("America/New_York"),
        },
    )()

    class CalendarStub:
        async def upcoming_context(self, days=14):
            return []

    class AgentStub:
        async def run(self, **kwargs):
            captured.update(kwargs)
            return {"text": "ok", "tool_calls": []}

    scheduler.calendar = CalendarStub()
    scheduler.agent = AgentStub()
    scheduler._tool_handlers = lambda **kwargs: {}

    from app.schemas.telegram import TelegramInboundMessage

    reply = await scheduler.handle_telegram_message(
        TelegramInboundMessage(
            chat_id="123",
            text="Set something for next Tuesday",
            message_id="1",
            sent_at=datetime.fromisoformat("2026-03-10T23:30:00+00:00"),
        )
    )

    assert reply == "ok"
    assert captured["extra_context"]["current_local_date"] == "2026-03-10"
    assert captured["extra_context"]["current_local_weekday"] == "Tuesday"
    assert captured["extra_context"]["current_local_datetime"].startswith("2026-03-10T19:30:00")


@pytest.mark.asyncio
async def test_handle_telegram_message_allows_send_email_tool():
    captured: dict = {}
    scheduler = SchedulerService.__new__(SchedulerService)
    scheduler.settings = type(
        "SettingsStub",
        (),
        {
            "app_timezone": "UTC",
            "timezone": __import__("zoneinfo").ZoneInfo("UTC"),
        },
    )()

    class CalendarStub:
        async def upcoming_context(self, days=14):
            return []

    class AgentStub:
        async def run(self, **kwargs):
            captured.update(kwargs)
            return {"text": "ok", "tool_calls": []}

    scheduler.calendar = CalendarStub()
    scheduler.agent = AgentStub()
    scheduler._tool_handlers = lambda **kwargs: {}

    from app.schemas.telegram import TelegramInboundMessage

    reply = await scheduler.handle_telegram_message(
        TelegramInboundMessage(
            chat_id="123",
            text="Email someone about a meeting",
            message_id="1",
            sent_at=datetime(2026, 3, 10, 12, 0, 0),
        )
    )

    assert reply == "ok"
    assert "send_email" in captured["allowed_tool_names"]


@pytest.mark.asyncio
async def test_is_trusted_email_sender_supports_sender_and_domain_allowlists():
    scheduler = SchedulerService.__new__(SchedulerService)
    scheduler.settings = type(
        "SettingsStub",
        (),
        {
            "email_trusted_senders": {"ceo@example.com"},
            "email_trusted_domains": {"partners.com"},
        },
    )()
    scheduler.thread_state = type(
        "ThreadStateStub",
        (),
        {"is_trusted_sender": staticmethod(lambda sender: _async_return(False))},
    )()

    assert await scheduler._is_email_sender_trusted("ceo@example.com")
    assert await scheduler._is_email_sender_trusted("someone@partners.com")
    assert not await scheduler._is_email_sender_trusted("outsider@other.com")


@pytest.mark.asyncio
async def test_handle_email_blocks_untrusted_sender_when_policy_enabled():
    scheduler = SchedulerService.__new__(SchedulerService)
    scheduler.settings = type(
        "SettingsStub",
        (),
        {
            "app_timezone": "UTC",
            "email_require_trust_for_automation": True,
            "email_trusted_senders": {"trusted@example.com"},
            "email_trusted_domains": {"example.com"},
        },
    )()

    class ThreadRecordStub:
        thread_id = "thread-1"
        subject = "Test"
        participants_json = '["attacker@evil.com"]'
        status = ThreadStatus.NEW_REQUEST
        approved_for_automation = False
        summary = None
        last_message_id = "msg-1"
        last_decision = None
        updated_at = datetime.now(UTC)

    class ThreadStateStub:
        def __init__(self):
            self.marked = None
            self.queued = None
            self.audit = []

        async def is_processed(self, event_id):
            return False

        async def is_trusted_sender(self, sender):
            return False

        async def get_thread(self, thread_id):
            return None

        async def upsert_thread(self, **kwargs):
            return ThreadRecordStub()

        async def queue_pending_email_approval(self, **kwargs):
            self.queued = kwargs

        async def mark_processed(self, event_id, source):
            self.marked = (event_id, source)

        async def add_security_audit_event(self, **kwargs):
            self.audit.append(kwargs)

    class TelegramStub:
        def __init__(self):
            self.messages = []

        async def send_message(self, text, chat_id=None):
            self.messages.append((text, chat_id))

    class AgentStub:
        async def run(self, **kwargs):
            raise AssertionError("Agent should not run for untrusted email when policy is enabled.")

    scheduler.thread_state = ThreadStateStub()
    scheduler.telegram = TelegramStub()
    scheduler.agent = AgentStub()
    scheduler.calendar = None
    scheduler.agentmail = None

    envelope = AgentMailEnvelope(
        event_id="evt-1",
        event_type="message.received",
        inbox_id="inbox-1",
        thread_id="thread-1",
        message_id="msg-1",
        subject="Schedule a meeting",
        sender="attacker@evil.com",
        to=["assistant@example.agentmail.to"],
        cc=[],
        preview="Can we meet next Tuesday?",
        body_text="Can we meet next Tuesday?",
        received_at=datetime(2026, 3, 10, 13, 0, 0, tzinfo=UTC),
    )

    result = await scheduler.handle_email(envelope)

    assert result["status"] == "blocked"
    assert result["reason"] == "untrusted_thread"
    assert scheduler.thread_state.marked == ("evt-1", "agentmail")
    assert scheduler.thread_state.queued is not None
    assert scheduler.telegram.messages
    assert "🚫 Email automation blocked for untrusted sender" in scheduler.telegram.messages[0][0]
    assert "/trust_sender attacker@evil.com" in scheduler.telegram.messages[0][0]


@pytest.mark.asyncio
async def test_handle_email_allows_untrusted_sender_on_approved_thread():
    captured: dict = {}
    scheduler = SchedulerService.__new__(SchedulerService)
    scheduler.settings = type(
        "SettingsStub",
        (),
        {
            "app_timezone": "UTC",
            "email_require_trust_for_automation": True,
            "email_trusted_senders": {"trusted@example.com"},
            "email_trusted_domains": {"example.com"},
        },
    )()

    class ThreadRecordStub:
        thread_id = "thread-1"
        subject = "Test"
        participants_json = '["trusted@example.com","outside@vendor.com"]'
        status = ThreadStatus.TIMES_PROPOSED
        approved_for_automation = True
        summary = "approved"
        last_message_id = "msg-1"
        last_decision = "reply_email"
        updated_at = datetime.now(UTC)

    class ThreadStateStub:
        def __init__(self):
            self.marked = None
            self.upsert_kwargs = None

        async def is_processed(self, event_id):
            return False

        async def is_trusted_sender(self, sender):
            return False

        async def get_thread(self, thread_id):
            return ThreadRecordStub()

        async def upsert_thread(self, **kwargs):
            self.upsert_kwargs = kwargs
            return ThreadRecordStub()

        async def list_active_proposals(self, thread_id):
            return []

        async def list_thread_calendar_event_ids(self, thread_id):
            return []

        async def mark_processed(self, event_id, source):
            self.marked = (event_id, source)

    class CalendarStub:
        async def upcoming_context(self, days=14):
            return []

    class AgentStub:
        async def run(self, **kwargs):
            captured.update(kwargs)
            return {"text": "processed", "tool_calls": []}

    class TelegramStub:
        def __init__(self):
            self.messages = []

        async def send_message(self, text, chat_id=None):
            self.messages.append((text, chat_id))

    scheduler.thread_state = ThreadStateStub()
    scheduler.telegram = TelegramStub()
    scheduler.agent = AgentStub()
    scheduler.calendar = CalendarStub()
    scheduler.agentmail = None

    envelope = AgentMailEnvelope(
        event_id="evt-2",
        event_type="message.received",
        inbox_id="inbox-1",
        thread_id="thread-1",
        message_id="msg-2",
        subject="Re: Schedule a meeting",
        sender="outside@vendor.com",
        to=["assistant@example.agentmail.to"],
        cc=["trusted@example.com"],
        preview="Tuesday works for me.",
        body_text="Tuesday works for me.",
        received_at=datetime(2026, 3, 10, 13, 0, 0, tzinfo=UTC),
    )

    result = await scheduler.handle_email(envelope)

    assert result["text"] == "processed"
    assert captured["extra_context"]["sender_trusted"] is False
    assert captured["extra_context"]["thread_approved_for_automation"] is True
    assert scheduler.thread_state.upsert_kwargs["approved_for_automation"] is True
    assert scheduler.thread_state.marked == ("evt-2", "agentmail")


@pytest.mark.asyncio
async def test_send_email_tool_uses_configured_inbox_for_operator_requests():
    scheduler = SchedulerService.__new__(SchedulerService)
    scheduler.settings = type(
        "SettingsStub",
        (),
        {
            "agentmail_inbox_address": "assistant@example.agentmail.to",
        },
    )()

    class AgentMailStub:
        def __init__(self):
            self.request = None

        async def send_email(self, request):
            self.request = request
            return {"status": "sent", "message_id": "msg-1", "thread_id": "thread-1"}

    scheduler.agentmail = AgentMailStub()
    scheduler.telegram = None
    scheduler.thread_state = None

    handlers = scheduler._tool_handlers(source="telegram")
    result = await handlers["send_email"](
        {
            "to": ["outside@example.com"],
            "subject": "Meeting coordination",
            "body_text": "Can we meet next week?",
        }
    )

    assert result["status"] == "sent"
    assert scheduler.agentmail.request.inbox_id == "assistant@example.agentmail.to"
    assert scheduler.agentmail.request.to == ["outside@example.com"]
    assert scheduler.agentmail.request.subject == "Meeting coordination"


@pytest.mark.asyncio
async def test_send_email_tool_allows_trusted_email_sender_to_initiate_outbound_email():
    scheduler = SchedulerService.__new__(SchedulerService)
    scheduler.settings = type(
        "SettingsStub",
        (),
        {
            "agentmail_inbox_address": "assistant@example.agentmail.to",
            "email_trusted_senders": set(),
            "email_trusted_domains": {"example.com"},
        },
    )()

    class AgentMailStub:
        def __init__(self):
            self.request = None

        async def send_email(self, request):
            self.request = request
            return {"status": "sent", "message_id": "msg-1", "thread_id": "thread-1"}

    class ThreadStateStub:
        async def is_trusted_sender(self, sender):
            return False

    class TelegramStub:
        async def send_message(self, text, chat_id=None):
            raise AssertionError("No alert should be sent for trusted initiation.")

    scheduler.agentmail = AgentMailStub()
    scheduler.thread_state = ThreadStateStub()
    scheduler.telegram = TelegramStub()

    envelope = AgentMailEnvelope(
        event_id="evt-1",
        event_type="message.received",
        inbox_id="assistant@example.agentmail.to",
        thread_id="thread-1",
        message_id="msg-1",
        subject="Please coordinate",
        sender="ceo@example.com",
        to=["assistant@example.agentmail.to"],
        cc=[],
        preview="",
        body_text="",
        received_at=datetime(2026, 3, 10, 13, 0, 0, tzinfo=UTC),
    )

    handlers = scheduler._tool_handlers(source="email", envelope=envelope)
    result = await handlers["send_email"](
        {
            "to": ["outside@example.net"],
            "subject": "Coordination",
            "body_text": "Let's find time.",
        }
    )

    assert result["status"] == "sent"
    assert scheduler.agentmail.request.inbox_id == "assistant@example.agentmail.to"
    assert scheduler.agentmail.request.to == ["outside@example.net"]


@pytest.mark.asyncio
async def test_send_email_tool_blocks_untrusted_email_sender_from_initiating_outbound_email():
    scheduler = SchedulerService.__new__(SchedulerService)
    scheduler.settings = type(
        "SettingsStub",
        (),
        {
            "agentmail_inbox_address": "assistant@example.agentmail.to",
            "email_trusted_senders": set(),
            "email_trusted_domains": {"trusted.com"},
        },
    )()

    class AgentMailStub:
        async def send_email(self, request):
            raise AssertionError("Untrusted sender should not be allowed to send outbound email.")

    class ThreadStateStub:
        def __init__(self):
            self.audit = []

        async def is_trusted_sender(self, sender):
            return False

        async def add_security_audit_event(self, **kwargs):
            self.audit.append(kwargs)

    class TelegramStub:
        def __init__(self):
            self.messages = []

        async def send_message(self, text, chat_id=None):
            self.messages.append((text, chat_id))

    scheduler.agentmail = AgentMailStub()
    scheduler.thread_state = ThreadStateStub()
    scheduler.telegram = TelegramStub()

    envelope = AgentMailEnvelope(
        event_id="evt-2",
        event_type="message.received",
        inbox_id="assistant@example.agentmail.to",
        thread_id="thread-2",
        message_id="msg-2",
        subject="Please email my friend",
        sender="outside@vendor.com",
        to=["assistant@example.agentmail.to"],
        cc=[],
        preview="",
        body_text="",
        received_at=datetime(2026, 3, 10, 13, 0, 0, tzinfo=UTC),
    )

    handlers = scheduler._tool_handlers(source="email", envelope=envelope)
    result = await handlers["send_email"](
        {
            "to": ["another@example.net"],
            "subject": "New outreach",
            "body_text": "Hello there.",
        }
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "sender_not_trusted_to_initiate_outbound_email"
    assert scheduler.thread_state.audit
    assert scheduler.thread_state.audit[0]["action"] == "send_email"
    assert scheduler.telegram.messages
    assert "blocked outbound email initiation" in scheduler.telegram.messages[0][0]


@pytest.mark.asyncio
async def test_approve_sender_trusts_sender_and_processes_pending_emails():
    scheduler = SchedulerService.__new__(SchedulerService)
    scheduler.settings = type(
        "SettingsStub",
        (),
        {
            "app_timezone": "UTC",
            "email_require_trust_for_automation": True,
            "email_trusted_senders": set(),
            "email_trusted_domains": set(),
        },
    )()

    processed = []

    class ThreadStateStub:
        def __init__(self):
            self.trusted = []
            self.audit = []

        async def add_trusted_sender(self, sender):
            self.trusted.append(sender)

        async def list_pending_email_approvals(self, sender):
            envelope = AgentMailEnvelope(
                event_id="evt-3",
                event_type="message.received",
                inbox_id="inbox-1",
                thread_id="thread-3",
                message_id="msg-3",
                subject="Intro",
                sender=sender,
                to=["assistant@example.agentmail.to"],
                cc=[],
                preview="hello",
                body_text="hello",
                received_at=datetime(2026, 3, 10, 13, 0, 0, tzinfo=UTC),
            )
            return [
                type(
                    "ApprovalStub",
                    (),
                    {
                        "id": 1,
                        "envelope_json": envelope.model_dump_json(),
                    },
                )()
            ]

        async def delete_pending_email_approval(self, approval_id):
            processed.append(("deleted", approval_id))

        async def add_security_audit_event(self, **kwargs):
            self.audit.append(kwargs)

    async def fake_process(envelope, *, skip_processed_check=False):
        processed.append((envelope.sender, skip_processed_check))
        return {"status": "processed"}

    scheduler.thread_state = ThreadStateStub()
    scheduler._process_email_envelope = fake_process

    reply = await scheduler.approve_sender("new@sender.com")

    assert scheduler.thread_state.trusted == ["new@sender.com"]
    assert ("new@sender.com", True) in processed
    assert ("deleted", 1) in processed
    assert "Trusted sender added: new@sender.com." in reply


@pytest.mark.asyncio
async def test_approve_thread_processes_pending_thread_emails():
    scheduler = SchedulerService.__new__(SchedulerService)
    scheduler.settings = type("SettingsStub", (), {})()

    processed = []

    class ThreadRecordStub:
        thread_id = "thread-9"
        subject = "Subject"
        participants_json = '["a@example.com"]'
        status = ThreadStatus.NEW_REQUEST
        approved_for_automation = False
        summary = None
        last_message_id = "msg-1"
        last_decision = None

    class ThreadStateStub:
        def __init__(self):
            self.upserts = []
            self.audit = []

        async def get_thread(self, thread_id):
            return ThreadRecordStub()

        async def upsert_thread(self, **kwargs):
            self.upserts.append(kwargs)

        async def list_pending_email_approvals_by_thread(self, thread_id):
            envelope = AgentMailEnvelope(
                event_id="evt-9",
                event_type="message.received",
                inbox_id="inbox-1",
                thread_id=thread_id,
                message_id="msg-9",
                subject="Thread approval",
                sender="outside@example.com",
                to=["assistant@example.agentmail.to"],
                cc=[],
                preview="hello",
                body_text="hello",
                received_at=datetime(2026, 3, 10, 13, 0, 0, tzinfo=UTC),
            )
            return [type("ApprovalStub", (), {"id": 2, "envelope_json": envelope.model_dump_json()})()]

        async def delete_pending_email_approval(self, approval_id):
            processed.append(("deleted", approval_id))

        async def add_security_audit_event(self, **kwargs):
            self.audit.append(kwargs)

    async def fake_process(envelope, *, skip_processed_check=False):
        processed.append((envelope.thread_id, skip_processed_check))
        return {"status": "processed"}

    scheduler.thread_state = ThreadStateStub()
    scheduler._process_email_envelope = fake_process

    reply = await scheduler.approve_thread("thread-9")

    assert scheduler.thread_state.upserts[0]["approved_for_automation"] is True
    assert ("thread-9", True) in processed
    assert ("deleted", 2) in processed
    assert "Thread approved for automation: thread-9." in reply


@pytest.mark.asyncio
async def test_handle_duplicate_agentmail_event_alerts_after_threshold():
    scheduler = SchedulerService.__new__(SchedulerService)

    class ThreadStateStub:
        def __init__(self):
            self.audit = []

        async def add_security_audit_event(self, **kwargs):
            self.audit.append(kwargs)

        async def count_recent_security_audit_events(self, **kwargs):
            return 3

    class TelegramStub:
        def __init__(self):
            self.messages = []

        async def send_message(self, text, chat_id=None):
            self.messages.append(text)

    scheduler.thread_state = ThreadStateStub()
    scheduler.telegram = TelegramStub()

    await scheduler.handle_duplicate_agentmail_event("evt-1")

    assert scheduler.thread_state.audit[0]["action"] == "duplicate_event"
    assert "AgentMail replay burst detected" in scheduler.telegram.messages[0]


@pytest.mark.asyncio
async def test_handle_unauthorized_telegram_access_records_and_alerts():
    scheduler = SchedulerService.__new__(SchedulerService)

    class ThreadStateStub:
        def __init__(self):
            self.audit = []

        async def add_security_audit_event(self, **kwargs):
            self.audit.append(kwargs)

    class TelegramStub:
        def __init__(self):
            self.messages = []

        async def send_message(self, text, chat_id=None):
            self.messages.append(text)

    scheduler.thread_state = ThreadStateStub()
    scheduler.telegram = TelegramStub()

    await scheduler.handle_unauthorized_telegram_access("999", "private")

    assert scheduler.thread_state.audit[0]["reason"] == "chat_not_allowlisted"
    assert "🚨 Security alert: unauthorized Telegram access blocked" in scheduler.telegram.messages[0]


@pytest.mark.asyncio
async def test_external_email_calendar_mutations_are_limited_to_bound_events():
    scheduler = SchedulerService.__new__(SchedulerService)

    class CalendarStub:
        def __init__(self):
            self.updated = []

        async def update_event(self, event):
            self.updated.append(event.event_id)
            return {"status": "updated", "event_id": event.event_id}

    scheduler.calendar = CalendarStub()
    scheduler.telegram = type("TelegramStub", (), {"send_message": staticmethod(_async_return)})()
    scheduler.thread_state = type(
        "ThreadStateStub",
        (),
        {
            "unbind_thread_calendar_event": staticmethod(_async_return),
            "add_security_audit_event": staticmethod(lambda **kwargs: _async_return(None)),
        },
    )()

    envelope = AgentMailEnvelope(
        event_id="evt-mail",
        event_type="message.received",
        inbox_id="inbox-1",
        thread_id="thread-1",
        message_id="msg-1",
        subject="Reschedule",
        sender="outside@vendor.com",
        to=["assistant@example.agentmail.to"],
        cc=[],
        preview="Can we move it?",
        body_text="Can we move it?",
        received_at=datetime(2026, 3, 10, 13, 0, 0, tzinfo=UTC),
    )

    handlers = scheduler._tool_handlers(
        source="email",
        envelope=envelope,
        restrict_calendar_mutations_to_thread_events=True,
        thread_bound_event_ids={"evt-bound"},
    )

    result = await handlers["update_event"]({"event_id": "evt-other", "title": "Moved"})

    assert result["status"] == "blocked"
    assert result["reason"] == "event_not_bound_to_thread"
    assert scheduler.calendar.updated == []


@pytest.mark.asyncio
async def test_trusted_email_calendar_mutations_can_update_unbound_events():
    scheduler = SchedulerService.__new__(SchedulerService)

    class CalendarStub:
        async def update_event(self, event):
            return {"status": "updated", "event_id": event.event_id}

    scheduler.calendar = CalendarStub()
    scheduler.thread_state = type("ThreadStateStub", (), {"unbind_thread_calendar_event": staticmethod(_async_return)})()

    envelope = AgentMailEnvelope(
        event_id="evt-mail",
        event_type="message.received",
        inbox_id="inbox-1",
        thread_id="thread-1",
        message_id="msg-1",
        subject="Reschedule",
        sender="trusted@example.com",
        to=["assistant@example.agentmail.to"],
        cc=[],
        preview="Please move this.",
        body_text="Please move this.",
        received_at=datetime(2026, 3, 10, 13, 0, 0, tzinfo=UTC),
    )

    handlers = scheduler._tool_handlers(
        source="email",
        envelope=envelope,
        restrict_calendar_mutations_to_thread_events=False,
        thread_bound_event_ids=set(),
    )

    result = await handlers["update_event"]({"event_id": "evt-unbound", "title": "Moved"})

    assert result["status"] == "updated"
    assert result["event_id"] == "evt-unbound"


@pytest.mark.asyncio
async def test_email_created_events_are_bound_to_thread():
    scheduler = SchedulerService.__new__(SchedulerService)

    class ThreadRecordStub:
        status = ThreadStatus.NEW_REQUEST
        participants_json = '["trusted@example.com"]'
        approved_for_automation = True
        summary = None

    class ThreadStateStub:
        def __init__(self):
            self.bound = []
            self.upserts = []

        async def get_thread(self, thread_id):
            return ThreadRecordStub()

        async def bind_thread_calendar_event(self, thread_id, event_id):
            self.bound.append((thread_id, event_id))

        async def upsert_thread(self, **kwargs):
            self.upserts.append(kwargs)

    class CalendarStub:
        async def create_event(self, event):
            return {"id": "evt-created"}

    class TelegramStub:
        async def send_message(self, text, chat_id=None):
            return None

    scheduler.thread_state = ThreadStateStub()
    scheduler.calendar = CalendarStub()
    scheduler.telegram = TelegramStub()

    envelope = AgentMailEnvelope(
        event_id="evt-mail",
        event_type="message.received",
        inbox_id="inbox-1",
        thread_id="thread-1",
        message_id="msg-1",
        subject="Schedule",
        sender="trusted@example.com",
        to=["assistant@example.agentmail.to"],
        cc=[],
        preview="Book it.",
        body_text="Book it.",
        received_at=datetime(2026, 3, 10, 13, 0, 0, tzinfo=UTC),
    )

    handlers = scheduler._tool_handlers(source="email", envelope=envelope)

    result = await handlers["create_event"](
        {
            "title": "Meeting",
            "start_at": "2026-03-12T10:00:00+00:00",
            "end_at": "2026-03-12T10:30:00+00:00",
            "timezone": "UTC",
        }
    )

    assert result["id"] == "evt-created"
    assert scheduler.thread_state.bound == [("thread-1", "evt-created")]


