import hmac
from hashlib import sha256

from app.integrations.agentmail import AgentMailService


def test_verify_signature():
    service = AgentMailService(
        api_base="https://api.agentmail.to",
        api_key=None,
        webhook_secret="secret",
    )
    body = b'{"hello":"world"}'
    signature = hmac.new(b"secret", body, sha256).hexdigest()

    assert service.verify_signature(body, signature) is True
    assert service.verify_signature(body, "bad") is False
