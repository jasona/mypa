from datetime import UTC, datetime, timedelta

import pytest
from redis.exceptions import AuthenticationError

from app.db.models import ProposalRecord, ThreadRecord, ThreadStatus
from app.db.store import SQLiteStore
from app.services.thread_state import ThreadStateStore


@pytest.mark.asyncio
async def test_thread_and_proposals_round_trip(tmp_path):
    store = SQLiteStore(tmp_path / "agent.db")
    await store.initialize()

    await store.upsert_thread(
        ThreadRecord(
            thread_id="thread-1",
            subject="Scheduling",
            participants_json='["a@example.com"]',
            status=ThreadStatus.NEW_REQUEST,
            approved_for_automation=True,
            summary="new request",
            intent_json='{"canonical_local_date":"2026-04-03"}',
            last_message_id="msg-1",
            last_decision="created",
            updated_at=datetime.now(UTC),
        )
    )

    thread = await store.get_thread("thread-1")
    assert thread is not None
    assert thread.subject == "Scheduling"
    assert thread.approved_for_automation is True
    assert thread.intent_json == '{"canonical_local_date":"2026-04-03"}'

    proposal = ProposalRecord(
        proposal_id="proposal-1",
        thread_id="thread-1",
        start_at=datetime.now(UTC),
        end_at=datetime.now(UTC) + timedelta(minutes=30),
        timezone="UTC",
    )
    await store.save_proposal(proposal)
    proposals = await store.list_active_proposals("thread-1")
    assert len(proposals) == 1


@pytest.mark.asyncio
async def test_processed_events_are_idempotent(tmp_path):
    store = SQLiteStore(tmp_path / "agent.db")
    await store.initialize()

    assert await store.is_event_processed("evt-1") is False
    await store.mark_event_processed("evt-1", "agentmail")
    assert await store.is_event_processed("evt-1") is True


@pytest.mark.asyncio
async def test_trusted_senders_and_pending_approvals_round_trip(tmp_path):
    store = SQLiteStore(tmp_path / "agent.db")
    await store.initialize()

    assert await store.is_trusted_sender("person@example.com") is False
    await store.add_trusted_sender("person@example.com")
    assert await store.is_trusted_sender("person@example.com") is True

    await store.queue_pending_email_approval(
        sender="person@example.com",
        event_id="evt-1",
        thread_id="thread-1",
        subject="Need approval",
        envelope_json='{"event_id":"evt-1"}',
    )
    pending = await store.list_pending_email_approvals("person@example.com")
    assert len(pending) == 1
    assert pending[0].thread_id == "thread-1"

    await store.delete_pending_email_approval(pending[0].id)
    assert await store.list_pending_email_approvals("person@example.com") == []


@pytest.mark.asyncio
async def test_thread_calendar_event_bindings_round_trip(tmp_path):
    store = SQLiteStore(tmp_path / "agent.db")
    await store.initialize()

    assert await store.is_thread_calendar_event_bound("thread-1", "evt-1") is False
    await store.bind_thread_calendar_event("thread-1", "evt-1")
    assert await store.is_thread_calendar_event_bound("thread-1", "evt-1") is True
    assert await store.list_thread_calendar_event_ids("thread-1") == ["evt-1"]

    await store.unbind_thread_calendar_event("thread-1", "evt-1")
    assert await store.list_thread_calendar_event_ids("thread-1") == []


@pytest.mark.asyncio
async def test_security_audit_events_round_trip(tmp_path):
    store = SQLiteStore(tmp_path / "agent.db")
    await store.initialize()

    await store.add_security_audit_event(
        source="telegram",
        actor="123",
        action="unauthorized_access",
        decision="denied",
        reason="chat_not_allowlisted",
        target="123",
        metadata_json='{"chat_type":"private"}',
    )

    recent = await store.count_recent_security_audit_events(
        source="telegram",
        action="unauthorized_access",
        target="123",
        since_iso="2000-01-01T00:00:00+00:00",
    )

    assert recent == 1

    events = await store.list_security_audit_events(limit=10, source="telegram")
    assert len(events) == 1
    assert events[0].action == "unauthorized_access"


@pytest.mark.asyncio
async def test_admin_read_models_round_trip(tmp_path):
    store = SQLiteStore(tmp_path / "agent.db")
    await store.initialize()

    await store.upsert_thread(
        ThreadRecord(
            thread_id="thread-1",
            subject="Customer follow up",
            participants_json='["admin@example.com","outside@example.com"]',
            status=ThreadStatus.AWAITING_CONFIRMATION,
            approved_for_automation=True,
            updated_at=datetime.now(UTC),
        )
    )
    await store.add_trusted_sender("outside@example.com")
    await store.queue_pending_email_approval(
        sender="outside@example.com",
        event_id="evt-1",
        thread_id="thread-1",
        subject="Need approval",
        envelope_json="{}",
    )
    await store.add_security_audit_event(
        source="agentmail",
        actor="outside@example.com",
        action="email_automation_gate",
        decision="denied",
        reason="thread_not_trusted_for_automation",
        target="thread-1",
    )
    await store.save_dead_letter(
        source="agentmail",
        event_id="evt-2",
        payload_json='{"event_id":"evt-2"}',
        error="boom",
    )

    threads = await store.list_threads(search="Customer", limit=10)
    assert len(threads) == 1
    assert threads[0].thread_id == "thread-1"

    trusted = await store.list_trusted_senders()
    assert [record.sender for record in trusted] == ["outside@example.com"]

    pending = await store.list_all_pending_email_approvals()
    assert len(pending) == 1
    assert pending[0].event_id == "evt-1"

    dead_letters = await store.list_dead_letters(limit=10)
    assert len(dead_letters) == 1
    assert dead_letters[0].event_id == "evt-2"

    summary = await store.get_dashboard_summary()
    assert summary["thread_count"] == 1
    assert summary["pending_approval_count"] == 1
    assert summary["dead_letter_count"] == 1
    assert summary["trusted_sender_count"] == 1


@pytest.mark.asyncio
async def test_thread_state_falls_back_to_sqlite_when_redis_fails(tmp_path):
    class FailingRedis:
        def __init__(self):
            self.closed = False

        async def get(self, key):
            raise AuthenticationError("Authentication required.")

        async def set(self, key, value, ex=None):
            raise AuthenticationError("Authentication required.")

        async def aclose(self):
            self.closed = True

    store = SQLiteStore(tmp_path / "agent.db")
    await store.initialize()
    await store.upsert_thread(
        ThreadRecord(
            thread_id="thread-1",
            subject="Fallback test",
            participants_json='["a@example.com"]',
            status=ThreadStatus.NEW_REQUEST,
            updated_at=datetime.now(UTC),
        )
    )

    redis_client = FailingRedis()
    thread_state = ThreadStateStore(sqlite_store=store, redis_client=redis_client)

    thread = await thread_state.get_thread("thread-1")

    assert thread is not None
    assert thread.subject == "Fallback test"
    assert thread_state.redis_client is None
    assert redis_client.closed is True
