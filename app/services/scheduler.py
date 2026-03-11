from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from uuid import uuid4

from app.config import Settings
from app.db.models import ProposalRecord, ThreadStatus
from app.db.store import SQLiteStore
from app.integrations.agentmail import AgentMailService
from app.integrations.calendar import CalendarAPIError, GoogleCalendarService
from app.integrations.telegram import TelegramBotService
from app.llm.claude_agent import ClaudeAgent
from app.schemas.calendar import AvailabilityRequest, CalendarEventInput, CalendarEventUpdate
from app.schemas.email import AgentMailEnvelope, EmailReplyRequest
from app.schemas.telegram import TelegramInboundMessage
from app.services.thread_state import ThreadStateStore

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(
        self,
        settings: Settings,
        agent: ClaudeAgent,
        calendar: GoogleCalendarService,
        agentmail: AgentMailService,
        telegram: TelegramBotService,
        thread_state: ThreadStateStore,
    ):
        self.settings = settings
        self.agent = agent
        self.calendar = calendar
        self.agentmail = agentmail
        self.telegram = telegram
        self.thread_state = thread_state

    async def handle_telegram_message(self, message: TelegramInboundMessage) -> str:
        extra_context = {
            "timezone": self.settings.app_timezone,
            "upcoming_events": await self.calendar.upcoming_context(days=14),
        }
        allowed_tool_names = {
            "check_availability",
            "create_event",
            "update_event",
            "delete_event",
        }
        try:
            result = await self.agent.run(
                prompt=f"Telegram message from operator:\n{message.text}",
                system_prompt=self._telegram_system_prompt(),
                tool_handlers=self._tool_handlers(source="telegram", telegram_message=message),
                extra_context=extra_context,
                allowed_tool_names=allowed_tool_names,
            )
            return result["text"] or "Request processed."
        except CalendarAPIError as exc:
            details = []
            if exc.status_code is not None:
                details.append(f"Google returned {exc.status_code}.")
            if exc.response_text:
                details.append(exc.response_text)
            suffix = f" {' '.join(details)}" if details else ""
            return f"I couldn't check that calendar right now.{suffix}"

    async def handle_email(self, envelope: AgentMailEnvelope) -> dict:
        if await self.thread_state.is_processed(envelope.event_id):
            return {"status": "ignored", "reason": "duplicate_event"}

        participants = sorted({envelope.sender, *envelope.to, *envelope.cc})
        existing = await self.thread_state.get_thread(envelope.thread_id)
        thread = await self.thread_state.upsert_thread(
            thread_id=envelope.thread_id,
            subject=envelope.subject,
            participants=participants,
            status=existing.status if existing else ThreadStatus.NEW_REQUEST,
            summary=existing.summary if existing else None,
            last_message_id=envelope.message_id,
            last_decision=existing.last_decision if existing else None,
        )

        active_proposals = await self.thread_state.list_active_proposals(envelope.thread_id)
        extra_context = {
            "timezone": self.settings.app_timezone,
            "thread": self._serialize_thread(thread),
            "current_message": {
                "inbox_id": envelope.inbox_id,
                "message_id": envelope.message_id,
                "thread_id": envelope.thread_id,
                "subject": envelope.subject,
                "sender": envelope.sender,
            },
            "active_proposals": [proposal.model_dump(mode="json") for proposal in active_proposals],
            "upcoming_events": await self.calendar.upcoming_context(days=14),
        }
        prompt = (
            "Inbound email received.\n"
            f"From: {envelope.sender}\n"
            f"Subject: {envelope.subject}\n"
            f"Body:\n{envelope.body_text}\n\n"
            "If replying by email, use the provided current_message inbox_id and message_id with reply_email.\n"
            "If the thread is about scheduling, use check_availability, reserve_slots, and reply_email.\n"
            "If a time is confirmed, create the event and notify the operator on Telegram.\n"
        )
        result = await self.agent.run(
            prompt=prompt,
            system_prompt=self._email_system_prompt(),
            tool_handlers=self._tool_handlers(source="email", envelope=envelope),
            extra_context=extra_context,
        )
        await self.thread_state.mark_processed(envelope.event_id, "agentmail")
        if result["text"]:
            logger.info("Email reasoning summary: %s", result["text"])
        return result

    async def notify_email_received(self, envelope: AgentMailEnvelope) -> None:
        subject = envelope.subject or "(no subject)"
        sender = envelope.sender or "unknown sender"
        summary = self.summarize_email(envelope)
        await self.telegram.send_message(
            "New email received\n"
            f"From: {sender}\n"
            f"Subject: {subject}\n"
            f"Summary: {summary}"
        )

    def _tool_handlers(
        self,
        *,
        source: str,
        envelope: AgentMailEnvelope | None = None,
        telegram_message: TelegramInboundMessage | None = None,
    ):
        async def message_telegram(payload: dict) -> dict:
            chat_id = payload.get("chat_id") or (telegram_message.chat_id if telegram_message else None)
            await self.telegram.send_message(text=payload["text"], chat_id=chat_id)
            return {"status": "sent"}

        async def check_availability(payload: dict) -> dict:
            request = AvailabilityRequest.model_validate(payload)
            result = await self.calendar.check_availability(request)
            return {
                "queried_calendar_ids": result.queried_calendar_ids,
                "busy_windows": [window.model_dump(mode="json") for window in result.busy_windows],
                "slots": [slot.model_dump(mode="json") for slot in result.slots[:10]],
            }

        async def reserve_slots(payload: dict) -> dict:
            thread_id = payload["thread_id"]
            timezone = payload["timezone"]
            saved = []
            for slot in payload["slots"]:
                proposal = ProposalRecord(
                    proposal_id=str(uuid4()),
                    thread_id=thread_id,
                    start_at=datetime.fromisoformat(slot["start_at"]),
                    end_at=datetime.fromisoformat(slot["end_at"]),
                    timezone=timezone,
                )
                await self.thread_state.save_proposal(proposal)
                saved.append(proposal.model_dump(mode="json"))
            current = await self.thread_state.get_thread(thread_id)
            await self.thread_state.upsert_thread(
                thread_id=thread_id,
                subject=current.subject if current else (envelope.subject if envelope else "Scheduling Thread"),
                participants=SQLiteStore.load_participants(current.participants_json) if current else [],
                status=ThreadStatus.TIMES_PROPOSED,
                summary=current.summary if current else None,
                last_message_id=current.last_message_id if current else None,
                last_decision="reserved_slots",
            )
            return {"status": "reserved", "proposals": saved}

        async def reply_email(payload: dict) -> dict:
            request = EmailReplyRequest.model_validate(payload)
            result = await self.agentmail.reply_email(request)
            if not envelope:
                return result
            current = await self.thread_state.get_thread(envelope.thread_id)
            if current:
                await self.thread_state.upsert_thread(
                    thread_id=current.thread_id,
                    subject=current.subject or envelope.subject,
                    participants=SQLiteStore.load_participants(current.participants_json),
                    status=ThreadStatus.AWAITING_CONFIRMATION,
                    summary=current.summary,
                    last_message_id=request.message_id,
                    last_decision="reply_email",
                )
            return result

        async def create_event(payload: dict) -> dict:
            event = CalendarEventInput.model_validate(payload)
            if envelope:
                current = await self.thread_state.get_thread(envelope.thread_id)
                if current and current.status == ThreadStatus.CONFIRMED:
                    return {"status": "skipped", "reason": "thread_already_confirmed"}
            result = await self.calendar.create_event(event)
            if envelope:
                current = await self.thread_state.get_thread(envelope.thread_id)
                participants = SQLiteStore.load_participants(current.participants_json) if current else []
                await self.thread_state.upsert_thread(
                    thread_id=envelope.thread_id,
                    subject=envelope.subject,
                    participants=participants,
                    status=ThreadStatus.CONFIRMED,
                    summary=current.summary if current else None,
                    last_message_id=envelope.message_id,
                    last_decision="create_event",
                )
                await self.telegram.send_message(
                    f"Meeting confirmed from {source}: {event.title} on {event.start_at.isoformat()}",
                )
            return result

        async def update_event(payload: dict) -> dict:
            event = CalendarEventUpdate.model_validate(payload)
            return await self.calendar.update_event(event)

        async def delete_event(payload: dict) -> dict:
            return await self.calendar.delete_event(payload["event_id"])

        return {
            "message_telegram": message_telegram,
            "check_availability": check_availability,
            "reserve_slots": reserve_slots,
            "reply_email": reply_email,
            "create_event": create_event,
            "update_event": update_event,
            "delete_event": delete_event,
        }

    def _telegram_system_prompt(self) -> str:
        return (
            "You are a concise personal assistant operating via Telegram. "
            "Use tools when live data or actions are required. "
            "If the user asks about coworkers, pass their names or email/calendar IDs via check_availability.calendar_ids. "
            "Prefer direct answers and keep the operator informed."
        )

    def _email_system_prompt(self) -> str:
        return (
            "You are a scheduling assistant handling inbound email threads. "
            "Before proposing times, check availability and reserve the slots. "
            "When a meeting is confirmed, create the calendar event and notify the operator via Telegram. "
            "Use professional email tone and avoid making unsupported assumptions."
        )

    @staticmethod
    def select_candidate_slots(
        slots: list[dict],
        count: int = 3,
        min_spacing_minutes: int = 60,
    ) -> list[dict]:
        selected: list[dict] = []
        min_spacing = timedelta(minutes=min_spacing_minutes)
        for slot in slots:
            start_at = datetime.fromisoformat(slot["start_at"])
            if selected and start_at - datetime.fromisoformat(selected[-1]["start_at"]) < min_spacing:
                continue
            selected.append(slot)
            if len(selected) >= count:
                break
        return selected

    @staticmethod
    def _serialize_thread(thread) -> dict:
        return {
            "thread_id": thread.thread_id,
            "subject": thread.subject,
            "participants": json.loads(thread.participants_json),
            "status": thread.status.value,
            "summary": thread.summary,
            "last_message_id": thread.last_message_id,
            "last_decision": thread.last_decision,
            "updated_at": thread.updated_at.isoformat(),
        }

    @staticmethod
    def summarize_email(envelope: AgentMailEnvelope) -> str:
        raw_text = envelope.preview or envelope.body_text or ""
        normalized = " ".join(raw_text.split())
        for marker in (" Best,", " Thanks,", " Regards,", " Sincerely,", " -- ", " From: "):
            if marker in normalized:
                normalized = normalized.split(marker, 1)[0].strip()
        if not normalized:
            return "No preview available."
        if len(normalized) <= 160:
            return normalized
        return normalized[:157].rstrip() + "..."
