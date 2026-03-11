from app.main import serialize_dead_letter_payload


def test_serialize_dead_letter_payload_redacts_email_bodies_and_trims_preview():
    payload = {
        "event_id": "evt-1",
        "preview": "x" * 20,
        "body_text": "secret body",
        "message": {
            "html": "<p>private</p>",
            "text": "also private",
        },
    }

    serialized = serialize_dead_letter_payload(payload, 10)

    assert '"body_text": "[redacted 11 chars]"' in serialized
    assert '"html": "[redacted 14 chars]"' in serialized
    assert '"text": "[redacted 12 chars]"' in serialized
    assert '"preview": "xxxxxxx..."' in serialized
