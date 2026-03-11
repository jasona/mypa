from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from redis.asyncio import Redis

from app.config import get_settings
from app.db.store import SQLiteStore
from app.integrations.agentmail import AgentMailAPIError, AgentMailService
from app.integrations.calendar import GoogleCalendarService
from app.integrations.telegram import TelegramBotService
from app.llm.claude_agent import ClaudeAgent
from app.logging import configure_logging
from app.services.scheduler import SchedulerService
from app.services.thread_state import ThreadStateStore

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)

    sqlite_store = SQLiteStore(settings.sqlite_file)
    await sqlite_store.initialize()

    redis_client = Redis.from_url(settings.redis_url) if settings.redis_url else None
    thread_state = ThreadStateStore(sqlite_store=sqlite_store, redis_client=redis_client)
    calendar_service = GoogleCalendarService(settings)
    agentmail_service = AgentMailService(
        api_base=settings.agentmail_api_base,
        api_key=settings.agentmail_api_key,
        webhook_secret=settings.agentmail_webhook_secret,
    )
    claude_agent = ClaudeAgent(settings)

    scheduler: SchedulerService | None = None

    async def on_telegram_message(message):
        assert scheduler is not None
        return await scheduler.handle_telegram_message(message)

    async def on_trust_sender(sender: str):
        assert scheduler is not None
        return await scheduler.approve_sender(sender)

    async def on_reject_sender(sender: str):
        assert scheduler is not None
        return await scheduler.reject_sender(sender)

    telegram_service = TelegramBotService(
        token=settings.telegram_bot_token,
        default_chat_id=settings.telegram_admin_chat_id,
        allowed_chat_ids=settings.telegram_allowed_chat_ids,
        allow_group_chats=settings.telegram_allow_group_chats,
        on_message=on_telegram_message,
        on_trust_sender=on_trust_sender,
        on_reject_sender=on_reject_sender,
    )
    scheduler = SchedulerService(
        settings=settings,
        agent=claude_agent,
        calendar=calendar_service,
        agentmail=agentmail_service,
        telegram=telegram_service,
        thread_state=thread_state,
    )

    app.state.settings = settings
    app.state.scheduler = scheduler
    app.state.agentmail = agentmail_service
    app.state.sqlite_store = sqlite_store
    app.state.redis = redis_client
    app.state.telegram = telegram_service

    await telegram_service.start()
    try:
        yield
    finally:
        await telegram_service.stop()
        if redis_client:
            await redis_client.aclose()


app = FastAPI(title="Persistent Agent Daemon", lifespan=lifespan)


@app.get("/health")
async def health(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    redis_client = request.app.state.redis
    redis_status = "disabled"
    if redis_client:
        try:
            await redis_client.ping()
            redis_status = "ok"
        except Exception:
            redis_status = "error"
    return {
        "status": "ok",
        "environment": settings.app_env,
        "telegram_enabled": bool(settings.telegram_bot_token),
        "anthropic_configured": bool(settings.anthropic_api_key),
        "google_calendar_configured": bool(settings.google_refresh_token),
        "redis_status": redis_status,
    }


@app.post("/webhooks/agentmail")
async def agentmail_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    raw_body = await request.body()
    agentmail = request.app.state.agentmail
    if not agentmail.verify_signature(raw_body, request.headers):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = await request.json()
    scheduler = request.app.state.scheduler
    sqlite_store = request.app.state.sqlite_store
    telegram = request.app.state.telegram
    settings = request.app.state.settings
    try:
        envelope = agentmail.parse_webhook(payload)
        background_tasks.add_task(process_agentmail_event, scheduler, sqlite_store, telegram, settings, payload, envelope)
        return {"status": "accepted", "event_type": envelope.event_type, "event_id": envelope.event_id}
    except Exception as exc:
        await sqlite_store.save_dead_letter(
            source="agentmail",
            payload_json=serialize_dead_letter_payload(payload, settings.dead_letter_payload_chars),
            error=str(exc),
            event_id=payload.get("event_id") or payload.get("id"),
        )
        await telegram.send_message(f"AgentMail webhook failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to process webhook") from exc


async def process_agentmail_event(scheduler, sqlite_store, telegram, settings, payload: dict, envelope) -> None:
    try:
        if envelope.event_type == "message.received":
            if await scheduler.thread_state.is_processed(envelope.event_id):
                logger.info("Ignoring duplicate AgentMail event: %s", envelope.event_id)
                return
            await scheduler.notify_email_received(envelope)
            await scheduler.handle_email(envelope)
            return
        logger.info("Ignoring unsupported AgentMail event type: %s", envelope.event_type)
    except Exception as exc:
        logger.exception("AgentMail background processing failed for event %s", envelope.event_id)
        await sqlite_store.save_dead_letter(
            source="agentmail",
            payload_json=serialize_dead_letter_payload(payload, settings.dead_letter_payload_chars),
            error=str(exc),
            event_id=payload.get("event_id") or payload.get("id"),
        )
        await telegram.send_message(format_background_error(exc))


def format_background_error(exc: Exception) -> str:
    if isinstance(exc, AgentMailAPIError):
        details = [f"AgentMail {exc.operation} failed"]
        if exc.status_code is not None:
            details.append(f"status: {exc.status_code}")
        if exc.response_text:
            details.append(f"response: {_trim_text(exc.response_text, 400)}")
        return "\n".join(details)
    return f"AgentMail background processing failed: {_trim_text(str(exc), 400)}"


def _trim_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def serialize_dead_letter_payload(payload: dict, max_chars: int) -> str:
    return json.dumps(_sanitize_dead_letter_value(payload, max_chars), default=str)


def _sanitize_dead_letter_value(value, max_chars: int, key_name: str | None = None):
    redacted_keys = {"body_text", "body_html", "quoted_text", "html", "text"}
    if isinstance(value, dict):
        return {key: _sanitize_dead_letter_value(item, max_chars, key) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_dead_letter_value(item, max_chars, key_name) for item in value]
    if isinstance(value, str):
        if key_name and key_name.lower() in redacted_keys:
            return f"[redacted {len(value)} chars]"
        return _trim_text(value, max_chars)
    return value
