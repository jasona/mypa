from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from app.db.models import ProposalRecord, ProposalStatus, ThreadRecord, ThreadStatus


class SQLiteStore:
    def __init__(self, path: Path):
        self.path = path

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS threads (
                    thread_id TEXT PRIMARY KEY,
                    subject TEXT,
                    participants_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT,
                    last_message_id TEXT,
                    last_decision TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS proposals (
                    proposal_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    start_at TEXT NOT NULL,
                    end_at TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_events (
                    event_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    processed_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS dead_letters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    event_id TEXT,
                    payload_json TEXT NOT NULL,
                    error TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            await db.commit()

    async def get_thread(self, thread_id: str) -> ThreadRecord | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT thread_id, subject, participants_json, status, summary, last_message_id, last_decision, updated_at
                FROM threads
                WHERE thread_id = ?
                """,
                (thread_id,),
            )
            row = await cursor.fetchone()
        if not row:
            return None
        return ThreadRecord(
            thread_id=row[0],
            subject=row[1],
            participants_json=row[2],
            status=ThreadStatus(row[3]),
            summary=row[4],
            last_message_id=row[5],
            last_decision=row[6],
            updated_at=datetime.fromisoformat(row[7]),
        )

    async def upsert_thread(self, record: ThreadRecord) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO threads (
                    thread_id, subject, participants_json, status, summary, last_message_id, last_decision, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET
                    subject = excluded.subject,
                    participants_json = excluded.participants_json,
                    status = excluded.status,
                    summary = excluded.summary,
                    last_message_id = excluded.last_message_id,
                    last_decision = excluded.last_decision,
                    updated_at = excluded.updated_at
                """,
                (
                    record.thread_id,
                    record.subject,
                    record.participants_json,
                    record.status.value,
                    record.summary,
                    record.last_message_id,
                    record.last_decision,
                    record.updated_at.isoformat(),
                ),
            )
            await db.commit()

    async def save_proposal(self, record: ProposalRecord) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO proposals (
                    proposal_id, thread_id, start_at, end_at, timezone, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(proposal_id) DO UPDATE SET
                    thread_id = excluded.thread_id,
                    start_at = excluded.start_at,
                    end_at = excluded.end_at,
                    timezone = excluded.timezone,
                    status = excluded.status,
                    created_at = excluded.created_at
                """,
                (
                    record.proposal_id,
                    record.thread_id,
                    record.start_at.isoformat(),
                    record.end_at.isoformat(),
                    record.timezone,
                    record.status.value,
                    record.created_at.isoformat(),
                ),
            )
            await db.commit()

    async def update_proposal_status(self, proposal_id: str, status: ProposalStatus) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE proposals SET status = ? WHERE proposal_id = ?",
                (status.value, proposal_id),
            )
            await db.commit()

    async def list_active_proposals(self, thread_id: str) -> list[ProposalRecord]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT proposal_id, thread_id, start_at, end_at, timezone, status, created_at
                FROM proposals
                WHERE thread_id = ? AND status = ?
                ORDER BY start_at ASC
                """,
                (thread_id, ProposalStatus.HELD.value),
            )
            rows = await cursor.fetchall()
        return [
            ProposalRecord(
                proposal_id=row[0],
                thread_id=row[1],
                start_at=datetime.fromisoformat(row[2]),
                end_at=datetime.fromisoformat(row[3]),
                timezone=row[4],
                status=ProposalStatus(row[5]),
                created_at=datetime.fromisoformat(row[6]),
            )
            for row in rows
        ]

    async def is_event_processed(self, event_id: str) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM processed_events WHERE event_id = ?",
                (event_id,),
            )
            row = await cursor.fetchone()
        return row is not None

    async def mark_event_processed(self, event_id: str, source: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO processed_events (event_id, source, processed_at)
                VALUES (?, ?, ?)
                """,
                (event_id, source, datetime.now(UTC).isoformat()),
            )
            await db.commit()

    async def save_dead_letter(
        self,
        *,
        source: str,
        payload_json: str,
        error: str,
        event_id: str | None = None,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO dead_letters (source, event_id, payload_json, error, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (source, event_id, payload_json, error, datetime.now(UTC).isoformat()),
            )
            await db.commit()

    @staticmethod
    def dump_participants(participants: list[str]) -> str:
        return json.dumps(participants)

    @staticmethod
    def load_participants(value: str) -> list[str]:
        if not value:
            return []
        return json.loads(value)
