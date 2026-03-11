from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.db.models import ProposalRecord, ThreadRecord, ThreadStatus
from app.db.store import SQLiteStore

logger = logging.getLogger(__name__)


class ThreadStateStore:
    def __init__(self, sqlite_store: SQLiteStore, redis_client: Redis | None = None):
        self.sqlite_store = sqlite_store
        self.redis_client = redis_client

    async def get_thread(self, thread_id: str) -> ThreadRecord | None:
        if self.redis_client:
            cached = await self._redis_get(self._thread_key(thread_id))
            if cached:
                return ThreadRecord.model_validate_json(cached)
        record = await self.sqlite_store.get_thread(thread_id)
        if record and self.redis_client:
            await self._redis_set(self._thread_key(thread_id), record.model_dump_json(), ex=7 * 24 * 3600)
        return record

    async def upsert_thread(
        self,
        thread_id: str,
        subject: str,
        participants: list[str],
        status: ThreadStatus,
        approved_for_automation: bool = False,
        summary: str | None = None,
        last_message_id: str | None = None,
        last_decision: str | None = None,
    ) -> ThreadRecord:
        record = ThreadRecord(
            thread_id=thread_id,
            subject=subject,
            participants_json=json.dumps(participants),
            status=status,
            approved_for_automation=approved_for_automation,
            summary=summary,
            last_message_id=last_message_id,
            last_decision=last_decision,
            updated_at=datetime.now(UTC),
        )
        await self.sqlite_store.upsert_thread(record)
        if self.redis_client:
            await self._redis_set(self._thread_key(thread_id), record.model_dump_json(), ex=7 * 24 * 3600)
        return record

    async def save_proposal(self, proposal: ProposalRecord) -> None:
        await self.sqlite_store.save_proposal(proposal)
        if self.redis_client:
            await self._redis_set(
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

    async def is_trusted_sender(self, sender: str) -> bool:
        return await self.sqlite_store.is_trusted_sender(sender)

    async def add_trusted_sender(self, sender: str) -> None:
        await self.sqlite_store.add_trusted_sender(sender)

    async def queue_pending_email_approval(
        self,
        *,
        sender: str,
        event_id: str,
        thread_id: str,
        subject: str | None,
        envelope_json: str,
    ) -> None:
        await self.sqlite_store.queue_pending_email_approval(
            sender=sender,
            event_id=event_id,
            thread_id=thread_id,
            subject=subject,
            envelope_json=envelope_json,
        )

    async def list_pending_email_approvals(self, sender: str):
        return await self.sqlite_store.list_pending_email_approvals(sender)

    async def delete_pending_email_approval(self, approval_id: int) -> None:
        await self.sqlite_store.delete_pending_email_approval(approval_id)

    async def delete_pending_email_approvals_for_sender(self, sender: str) -> int:
        return await self.sqlite_store.delete_pending_email_approvals_for_sender(sender)

    @staticmethod
    def _thread_key(thread_id: str) -> str:
        return f"thread:{thread_id}"

    @staticmethod
    def _proposal_key(proposal_id: str) -> str:
        return f"proposal:{proposal_id}"

    async def _redis_get(self, key: str) -> Any | None:
        if not self.redis_client:
            return None
        try:
            return await self.redis_client.get(key)
        except RedisError as exc:
            await self._disable_redis(exc)
            return None

    async def _redis_set(self, key: str, value: str, *, ex: int) -> None:
        if not self.redis_client:
            return
        try:
            await self.redis_client.set(key, value, ex=ex)
        except RedisError as exc:
            await self._disable_redis(exc)

    async def _disable_redis(self, exc: RedisError) -> None:
        if not self.redis_client:
            return
        logger.warning("Redis unavailable; falling back to SQLite only: %s", exc)
        client = self.redis_client
        self.redis_client = None
        try:
            await client.aclose()
        except Exception:
            logger.debug("Failed to close Redis client cleanly.", exc_info=True)
