from __future__ import annotations

import json
from datetime import UTC, datetime

from redis.asyncio import Redis

from app.db.models import ProposalRecord, ThreadRecord, ThreadStatus
from app.db.store import SQLiteStore


class ThreadStateStore:
    def __init__(self, sqlite_store: SQLiteStore, redis_client: Redis | None = None):
        self.sqlite_store = sqlite_store
        self.redis_client = redis_client

    async def get_thread(self, thread_id: str) -> ThreadRecord | None:
        if self.redis_client:
            cached = await self.redis_client.get(self._thread_key(thread_id))
            if cached:
                return ThreadRecord.model_validate_json(cached)
        record = await self.sqlite_store.get_thread(thread_id)
        if record and self.redis_client:
            await self.redis_client.set(self._thread_key(thread_id), record.model_dump_json(), ex=7 * 24 * 3600)
        return record

    async def upsert_thread(
        self,
        thread_id: str,
        subject: str,
        participants: list[str],
        status: ThreadStatus,
        summary: str | None = None,
        last_message_id: str | None = None,
        last_decision: str | None = None,
    ) -> ThreadRecord:
        record = ThreadRecord(
            thread_id=thread_id,
            subject=subject,
            participants_json=json.dumps(participants),
            status=status,
            summary=summary,
            last_message_id=last_message_id,
            last_decision=last_decision,
            updated_at=datetime.now(UTC),
        )
        await self.sqlite_store.upsert_thread(record)
        if self.redis_client:
            await self.redis_client.set(self._thread_key(thread_id), record.model_dump_json(), ex=7 * 24 * 3600)
        return record

    async def save_proposal(self, proposal: ProposalRecord) -> None:
        await self.sqlite_store.save_proposal(proposal)
        if self.redis_client:
            await self.redis_client.set(
                self._proposal_key(proposal.proposal_id),
                proposal.model_dump_json(),
                ex=7 * 24 * 3600,
            )

    async def list_active_proposals(self, thread_id: str) -> list[ProposalRecord]:
        return await self.sqlite_store.list_active_proposals(thread_id)

    async def is_processed(self, event_id: str) -> bool:
        return await self.sqlite_store.is_event_processed(event_id)

    async def mark_processed(self, event_id: str, source: str) -> None:
        await self.sqlite_store.mark_event_processed(event_id, source)

    @staticmethod
    def _thread_key(thread_id: str) -> str:
        return f"thread:{thread_id}"

    @staticmethod
    def _proposal_key(proposal_id: str) -> str:
        return f"proposal:{proposal_id}"
