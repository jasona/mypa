from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import ProposalRecord, ThreadRecord, ThreadStatus
from app.db.store import SQLiteStore


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
            summary="new request",
            last_message_id="msg-1",
            last_decision="created",
            updated_at=datetime.now(UTC),
        )
    )

    thread = await store.get_thread("thread-1")
    assert thread is not None
    assert thread.subject == "Scheduling"

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
