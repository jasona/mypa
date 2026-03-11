from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ThreadStatus(StrEnum):
    NEW_REQUEST = "new_request"
    AWAITING_INTERNAL_DECISION = "awaiting_internal_decision"
    TIMES_PROPOSED = "times_proposed"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    CLOSED = "closed"
    CONFLICT_DETECTED = "conflict_detected"


class ProposalStatus(StrEnum):
    HELD = "held"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ThreadRecord(BaseModel):
    thread_id: str
    subject: str | None = None
    participants_json: str = "[]"
    status: ThreadStatus = ThreadStatus.NEW_REQUEST
    approved_for_automation: bool = False
    summary: str | None = None
    last_message_id: str | None = None
    last_decision: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProposalRecord(BaseModel):
    proposal_id: str
    thread_id: str
    start_at: datetime
    end_at: datetime
    timezone: str
    status: ProposalStatus = ProposalStatus.HELD
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProcessedEventRecord(BaseModel):
    event_id: str
    source: str
    processed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TrustedSenderRecord(BaseModel):
    sender: str
    added_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PendingEmailApprovalRecord(BaseModel):
    id: int
    sender: str
    event_id: str
    thread_id: str
    subject: str | None = None
    envelope_json: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ThreadCalendarEventRecord(BaseModel):
    thread_id: str
    event_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
