from __future__ import annotations

import hmac
import logging
from hashlib import sha256
from typing import Any

import httpx
from pydantic import ValidationError

from app.schemas.email import AgentMailEnvelope, EmailReplyRequest
from app.services.reliability import retry_async

logger = logging.getLogger(__name__)


class AgentMailService:
    def __init__(self, api_base: str, api_key: str | None, webhook_secret: str | None):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.webhook_secret = webhook_secret

    def verify_signature(self, raw_body: bytes, signature: str | None) -> bool:
        if not self.webhook_secret:
            return True
        if not signature:
            return False
        digest = hmac.new(self.webhook_secret.encode("utf-8"), raw_body, sha256).hexdigest()
        return hmac.compare_digest(digest, signature)

    def parse_webhook(self, payload: dict[str, Any]) -> AgentMailEnvelope:
        event_id = str(payload.get("event_id") or payload.get("id"))
        thread_id = str(payload.get("thread_id") or payload.get("thread", {}).get("id"))
        message_id = str(payload.get("message_id") or payload.get("message", {}).get("id"))
        message = payload.get("message", {})
        if not event_id or event_id == "None":
            raise ValueError("AgentMail payload is missing event_id.")
        if not thread_id or thread_id == "None":
            raise ValueError("AgentMail payload is missing thread_id.")
        if not message_id or message_id == "None":
            raise ValueError("AgentMail payload is missing message_id.")
        try:
            return AgentMailEnvelope(
                event_id=event_id,
                thread_id=thread_id,
                message_id=message_id,
                subject=payload.get("subject") or message.get("subject") or "",
                sender=payload.get("from") or message.get("from") or "",
                to=payload.get("to") or message.get("to") or [],
                cc=payload.get("cc") or message.get("cc") or [],
                body_text=payload.get("body_text") or message.get("text") or "",
                body_html=payload.get("body_html") or message.get("html"),
                quoted_text=payload.get("quoted_text") or message.get("quoted_text"),
                received_at=payload.get("received_at") or message.get("received_at"),
            )
        except ValidationError as exc:
            logger.error("Invalid AgentMail payload: %s", exc)
            raise

    async def reply_email(self, request: EmailReplyRequest) -> dict[str, Any]:
        if not self.api_key:
            logger.warning("AgentMail API key missing; reply simulated for thread %s.", request.thread_id)
            return {"status": "simulated", "thread_id": request.thread_id}

        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "thread_id": request.thread_id,
            "subject": request.subject,
            "text": request.body_text,
            "to": request.to,
            "cc": request.cc,
            "in_reply_to": request.in_reply_to,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            async def do_request() -> dict[str, Any]:
                response = await client.post(f"{self.api_base}/v1/messages/reply", json=payload, headers=headers)
                response.raise_for_status()
                return response.json()

            return await retry_async(
                do_request,
                attempts=3,
                delay_seconds=1.0,
                retry_exceptions=(httpx.HTTPError,),
            )
