from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from redis.asyncio import Redis

from app.config import get_settings
from app.db.store import SQLiteStore
from app.integrations.agentmail import AgentMailService
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

    telegram_service = TelegramBotService(
        token=settings.telegram_bot_token,
        default_chat_id=settings.telegram_admin_chat_id,
        on_message=on_telegram_message,
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
    try:
        envelope = agentmail.parse_webhook(payload)
        background_tasks.add_task(process_agentmail_event, scheduler, sqlite_store, telegram, payload, envelope)
        return {"status": "accepted", "event_type": envelope.event_type, "event_id": envelope.event_id}
    except Exception as exc:
        await sqlite_store.save_dead_letter(
            source="agentmail",
            payload_json=json.dumps(payload, default=str),
            error=str(exc),
            event_id=payload.get("event_id") or payload.get("id"),
        )
        await telegram.send_message(f"AgentMail webhook failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to process webhook") from exc


async def process_agentmail_event(scheduler, sqlite_store, telegram, payload: dict, envelope) -> None:
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
        await sqlite_store.save_dead_letter(
            source="agentmail",
            payload_json=json.dumps(payload, default=str),
            error=str(exc),
            event_id=payload.get("event_id") or payload.get("id"),
        )
        await telegram.send_message(f"AgentMail background processing failed: {exc}")
