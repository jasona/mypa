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
            last_message_id="msg-1",
            last_decision="created",
            updated_at=datetime.now(UTC),
        )
    )

    thread = await store.get_thread("thread-1")
    assert thread is not None
    assert thread.subject == "Scheduling"
    assert thread.approved_for_automation is True

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
