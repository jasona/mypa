from app.integrations.agentmail import AgentMailService


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
    assert envelope.thread_id == "thd_456"
    assert envelope.message_id == "<msg_789@agentmail.to>"
    assert envelope.sender == "sender@example.com"
    assert envelope.sender_addresses == ["sender@example.com"]
    assert envelope.subject == "Email Subject"
    assert envelope.preview == "A short preview of the email text..."
