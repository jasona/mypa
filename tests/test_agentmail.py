import pytest

from app.integrations.agentmail import AgentMailService
from app.schemas.email import EmailReplyRequest


def test_verify_signature_skips_when_secret_missing():
    service = AgentMailService(
        api_base="https://api.agentmail.to",
        api_key=None,
        webhook_secret=None,
    )
    body = b'{"hello":"world"}'

    assert service.verify_signature(body, {}) is True


def test_verify_signature_requires_svix_headers():
    service = AgentMailService(
        api_base="https://api.agentmail.to",
        api_key=None,
        webhook_secret="whsec_test_secret",
    )
    body = b'{"hello":"world"}'

    assert service.verify_signature(body, {}) is False


def test_parse_message_received_webhook():
    service = AgentMailService(
        api_base="https://api.agentmail.to",
        api_key=None,
        webhook_secret=None,
    )
    payload = {
        "event_type": "message.received",
        "event_id": "evt_123abc",
        "message": {
            "from_": ["sender@example.com"],
            "inbox_id": "inbox_123",
            "thread_id": "thd_456",
            "message_id": "<msg_789@agentmail.to>",
            "timestamp": "2023-10-27T10:00:00Z",
            "to": ["recipient@example.com"],
            "cc": ["cc@example.com"],
            "subject": "Email Subject",
            "preview": "A short preview of the email text...",
            "text": "The full text body of the email.",
            "html": "<html>...</html>",
        },
    }

    envelope = service.parse_webhook(payload)

    assert envelope.event_type == "message.received"
    assert envelope.event_id == "evt_123abc"
    assert envelope.inbox_id == "inbox_123"
    assert envelope.thread_id == "thd_456"
    assert envelope.message_id == "<msg_789@agentmail.to>"
    assert envelope.sender == "sender@example.com"
    assert envelope.sender_addresses == ["sender@example.com"]
    assert envelope.subject == "Email Subject"
    assert envelope.preview == "A short preview of the email text..."


@pytest.mark.asyncio
async def test_reply_email_uses_documented_agentmail_endpoint(monkeypatch):
    captured: dict = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message_id": "reply_123", "thread_id": "thread_123"}

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json, headers):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return DummyResponse()

    monkeypatch.setattr("app.integrations.agentmail.httpx.AsyncClient", lambda timeout: DummyClient())

    service = AgentMailService(
        api_base="https://api.agentmail.to",
        api_key="token_123",
        webhook_secret=None,
    )
    result = await service.reply_email(
        EmailReplyRequest(
            inbox_id="inbox_123",
            message_id="msg_456",
            body_text="Plain text reply",
            body_html="<p>Plain text reply</p>",
            to=["recipient@example.com"],
            cc=["cc@example.com"],
            reply_all=True,
        )
    )

    assert result == {"message_id": "reply_123", "thread_id": "thread_123"}
    assert captured["url"] == "https://api.agentmail.to/v0/inboxes/inbox_123/messages/msg_456/reply"
    assert captured["json"] == {
        "text": "Plain text reply",
        "html": "<p>Plain text reply</p>",
        "to": ["recipient@example.com"],
        "cc": ["cc@example.com"],
        "reply_all": True,
    }
    assert captured["headers"]["Authorization"] == "Bearer token_123"
