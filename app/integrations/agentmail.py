from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import ValidationError
from svix.webhooks import Webhook, WebhookVerificationError

from app.schemas.email import AgentMailEnvelope, EmailReplyRequest
from app.services.reliability import retry_async

logger = logging.getLogger(__name__)


class AgentMailAPIError(RuntimeError):
    def __init__(
        self,
        *,
        operation: str,
        message: str,
        status_code: int | None = None,
        response_text: str | None = None,
        url: str | None = None,
    ):
        super().__init__(message)
        self.operation = operation
        self.status_code = status_code
        self.response_text = response_text
        self.url = url


class AgentMailService:
    def __init__(self, api_base: str, api_key: str | None, webhook_secret: str | None):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.webhook_secret = webhook_secret

    def verify_signature(self, raw_body: bytes, headers: Mapping[str, str]) -> bool:
        if not self.webhook_secret:
            return True
        svix_headers = {
            "svix-id": headers.get("svix-id"),
            "svix-timestamp": headers.get("svix-timestamp"),
            "svix-signature": headers.get("svix-signature"),
        }
        if not all(svix_headers.values()):
            return False
        try:
            Webhook(self.webhook_secret).verify(raw_body.decode("utf-8"), svix_headers)
            return True
        except WebhookVerificationError:
            return False

    def parse_webhook(self, payload: dict[str, Any]) -> AgentMailEnvelope:
        event_type = str(payload.get("event_type") or "message.received")
        event_id = payload.get("event_id") or payload.get("id")
        inbox_id = payload.get("inbox_id") or payload.get("message", {}).get("inbox_id") or payload.get("thread", {}).get("inbox_id")
        thread_id = payload.get("thread_id") or payload.get("thread", {}).get("id")
        message_id = payload.get("message_id") or payload.get("message", {}).get("id")
        message = payload.get("message", {})
        from_values = payload.get("from_") or payload.get("from") or message.get("from_") or message.get("from") or []
        sender_addresses = self._coerce_address_list(from_values)
        to_addresses = self._coerce_address_list(payload.get("to") or message.get("to") or [])
        cc_addresses = self._coerce_address_list(payload.get("cc") or message.get("cc") or [])
        event_id = str(event_id) if event_id is not None else None
        inbox_id = str(inbox_id) if inbox_id is not None else None
        thread_id = str(thread_id or message.get("thread_id")) if (thread_id or message.get("thread_id")) is not None else None
        message_id = (
            str(message_id or message.get("message_id"))
            if (message_id or message.get("message_id")) is not None
            else None
        )
        if not event_id or event_id == "None":
            raise ValueError("AgentMail payload is missing event_id.")
        if not inbox_id or inbox_id == "None":
            raise ValueError("AgentMail payload is missing inbox_id.")
        if not thread_id or thread_id == "None":
            raise ValueError("AgentMail payload is missing thread_id.")
        if not message_id or message_id == "None":
            raise ValueError("AgentMail payload is missing message_id.")
        try:
            return AgentMailEnvelope(
                event_type=event_type,
                event_id=event_id,
                inbox_id=inbox_id,
                thread_id=thread_id,
                message_id=message_id,
                subject=payload.get("subject") or message.get("subject") or "",
                sender=sender_addresses[0] if sender_addresses else "unknown sender",
                sender_addresses=sender_addresses,
                to=to_addresses,
                cc=cc_addresses,
                preview=payload.get("preview") or message.get("preview") or "",
                body_text=payload.get("body_text") or message.get("text") or "",
                body_html=payload.get("body_html") or message.get("html"),
                quoted_text=payload.get("quoted_text") or message.get("quoted_text"),
                received_at=(
                    payload.get("received_at")
                    or message.get("timestamp")
                    or message.get("created_at")
                    or message.get("updated_at")
                    or message.get("received_at")
                ),
            )
        except ValidationError as exc:
            logger.error("Invalid AgentMail payload: %s", exc)
            raise

    @staticmethod
    def _coerce_address_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    async def reply_email(self, request: EmailReplyRequest) -> dict[str, Any]:
        if not self.api_key:
            logger.warning("AgentMail API key missing; reply simulated for message %s.", request.message_id)
            return {"status": "simulated", "message_id": request.message_id, "thread_id": None}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "text": request.body_text,
            "html": request.body_html,
            "to": request.to,
            "cc": request.cc,
            "bcc": request.bcc,
            "reply_to": request.reply_to,
            "reply_all": request.reply_all,
        }
        url = f"{self.api_base}/v0/inboxes/{request.inbox_id}/messages/{request.message_id}/reply"
        async with httpx.AsyncClient(timeout=30.0) as client:
            async def do_request() -> dict[str, Any]:
                response = await client.post(
                    url,
                    json={key: value for key, value in payload.items() if value not in (None, [], "")},
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()

            try:
                return await retry_async(
                    do_request,
                    attempts=3,
                    delay_seconds=1.0,
                    retry_exceptions=(httpx.HTTPError,),
                )
            except httpx.HTTPStatusError as exc:
                response_text = exc.response.text if exc.response is not None else None
                raise AgentMailAPIError(
                    operation="reply_email",
                    message=(
                        f"AgentMail reply failed with status {exc.response.status_code}"
                        if exc.response is not None
                        else "AgentMail reply failed with HTTP status error"
                    ),
                    status_code=exc.response.status_code if exc.response is not None else None,
                    response_text=response_text,
                    url=str(exc.request.url) if exc.request is not None else url,
                ) from exc
            except httpx.RequestError as exc:
                raise AgentMailAPIError(
                    operation="reply_email",
                    message=f"AgentMail request failed: {exc}",
                    url=str(exc.request.url) if exc.request is not None else url,
                ) from exc
