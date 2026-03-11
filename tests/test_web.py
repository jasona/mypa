import re
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app.db.models import DeadLetterRecord, PendingEmailApprovalRecord, SecurityAuditRecord
from app.web.routes import router as admin_router


class ThreadStateStub:
    async def get_dashboard_summary(self):
        return {
            "thread_count": 3,
            "pending_approval_count": 1,
            "dead_letter_count": 1,
            "trusted_sender_count": 2,
            "recent_security_event_count": 4,
        }

    async def list_all_pending_email_approvals(self):
        return [
            PendingEmailApprovalRecord(
                id=1,
                sender="outside@example.com",
                event_id="evt-1",
                thread_id="thread-1",
                subject="Need help",
                envelope_json="{}",
                created_at=datetime.now(UTC),
            )
        ]

    async def list_security_audit_events(self, **kwargs):
        return [
            SecurityAuditRecord(
                id=1,
                source="telegram",
                actor="admin",
                action="approve_sender",
                decision="allowed",
                reason="admin_approved_sender",
                target="outside@example.com",
                metadata_json="{}",
                created_at=datetime.now(UTC),
            )
        ]

    async def list_dead_letters(self, **kwargs):
        return [
            DeadLetterRecord(
                id=1,
                source="agentmail",
                event_id="evt-2",
                payload_json='{"event_id":"evt-2"}',
                error="boom",
                created_at=datetime.now(UTC),
            )
        ]

    async def list_trusted_senders(self):
        return []

    async def list_threads(self, **kwargs):
        return []

    async def get_thread(self, thread_id):
        return None

    async def list_proposals(self, thread_id):
        return []

    async def list_pending_email_approvals_by_thread(self, thread_id):
        return []

    async def list_thread_calendar_event_ids(self, thread_id):
        return []


class SchedulerStub:
    def __init__(self):
        self.thread_state = ThreadStateStub()
        self.approved_senders = []
        self.browser_prompts = []

    async def approve_sender(self, sender: str):
        self.approved_senders.append(sender)
        return "ok"

    async def reject_sender(self, sender: str):
        return "ok"

    async def approve_thread(self, thread_id: str):
        return "ok"

    async def reject_thread(self, thread_id: str):
        return "ok"

    async def handle_browser_operator_message(self, text: str):
        self.browser_prompts.append(text)
        return f"handled: {text}"


def _build_client():
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret", same_site="lax", https_only=False)
    app.include_router(admin_router)
    app.state.settings = SimpleNamespace(
        web_admin_enabled=True,
        web_admin_password="secret",
        email_trusted_senders={"ops@example.com"},
        email_trusted_domains={"example.com"},
        app_env="test",
        app_timezone="UTC",
        web_session_max_age_seconds=3600,
        telegram_admin_chat_id="123",
        telegram_allowed_chat_ids={"123"},
        telegram_allow_group_chats=False,
        email_require_trust_for_automation=True,
        google_refresh_token="configured",
        agentmail_api_key="configured",
        agentmail_webhook_secret="configured",
        anthropic_api_key="configured",
        redis_url=None,
    )
    app.state.scheduler = SchedulerStub()
    app.state.sqlite_store = SimpleNamespace(load_participants=lambda value: [])
    return TestClient(app), app.state.scheduler


def _extract_csrf(response_text: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', response_text)
    assert match is not None
    return match.group(1)


def test_web_admin_login_dashboard_and_actions():
    client, scheduler = _build_client()

    login_page = client.get("/admin/login")
    assert login_page.status_code == 200
    csrf_token = _extract_csrf(login_page.text)

    login_response = client.post(
        "/admin/login",
        data={"password": "secret", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert login_response.status_code == 303
    assert login_response.headers["location"] == "/admin"

    dashboard = client.get("/admin")
    assert dashboard.status_code == 200
    assert "Pending Approvals" in dashboard.text
    assert "outside@example.com" in dashboard.text

    approvals_page = client.get("/admin/pending-approvals")
    approval_csrf = _extract_csrf(approvals_page.text)
    approve_response = client.post(
        "/admin/actions/trust-sender",
        data={
            "sender": "outside@example.com",
            "redirect_to": "/admin/pending-approvals",
            "csrf_token": approval_csrf,
        },
        follow_redirects=False,
    )
    assert approve_response.status_code == 303
    assert scheduler.approved_senders == ["outside@example.com"]


def test_operator_tools_reuse_scheduler_flow():
    client, scheduler = _build_client()

    login_page = client.get("/admin/login")
    csrf_token = _extract_csrf(login_page.text)
    client.post("/admin/login", data={"password": "secret", "csrf_token": csrf_token})

    tools_page = client.get("/admin/tools")
    tool_csrf = _extract_csrf(tools_page.text)
    response = client.post(
        "/admin/tools/message",
        data={"operator_prompt": "Move my 2pm meeting to tomorrow.", "csrf_token": tool_csrf},
    )

    assert response.status_code == 200
    assert "handled: Move my 2pm meeting to tomorrow." in response.text
    assert scheduler.browser_prompts == ["Move my 2pm meeting to tomorrow."]
