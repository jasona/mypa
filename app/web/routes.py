from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.db.models import ThreadStatus
from app.web.auth import (
    ensure_csrf_token,
    is_authenticated,
    login,
    logout,
    pop_flash,
    require_authenticated,
    require_web_admin_enabled,
    set_flash,
    validate_csrf,
)

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))


def _render(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        name,
        {
            "csrf_token": ensure_csrf_token(request),
            "flash": pop_flash(request),
            "current_path": request.url.path,
            **context,
        },
        status_code=status_code,
    )


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


def _safe_redirect_target(value: str) -> str:
    if value.startswith("/admin"):
        return value
    return "/admin"


def _participants(request: Request, participants_json: str) -> list[str]:
    return request.app.state.sqlite_store.load_participants(participants_json)


def _pretty_json(value: str) -> str:
    try:
        return json.dumps(json.loads(value), indent=2, sort_keys=True)
    except json.JSONDecodeError:
        return value


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> Response:
    require_web_admin_enabled(request)
    if is_authenticated(request):
        return _redirect("/admin")
    return _render(request, "admin/login.html")


@router.post("/login")
async def login_submit(
    request: Request,
    password: str = Form(...),
    csrf_token: str = Form(...),
) -> Response:
    require_web_admin_enabled(request)
    validate_csrf(request, csrf_token)
    if login(request, password):
        set_flash(request, "success", "Signed in to the admin console.")
        return _redirect("/admin")
    set_flash(request, "error", "Invalid password.")
    return _render(request, "admin/login.html", status_code=status.HTTP_401_UNAUTHORIZED)


@router.post("/logout")
async def logout_submit(request: Request, csrf_token: str = Form(...)) -> Response:
    require_web_admin_enabled(request)
    validate_csrf(request, csrf_token)
    logout(request)
    return _redirect("/admin/login")


@router.get("", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    require_authenticated(request)
    thread_state = request.app.state.scheduler.thread_state
    summary = await thread_state.get_dashboard_summary()
    approvals = await thread_state.list_all_pending_email_approvals()
    audits = await thread_state.list_security_audit_events(limit=12)
    dead_letters = await thread_state.list_dead_letters(limit=12)
    return _render(
        request,
        "admin/dashboard.html",
        summary=summary,
        recent_approvals=approvals[:10],
        recent_audits=audits[:10],
        recent_dead_letters=dead_letters[:10],
    )


@router.get("/threads", response_class=HTMLResponse)
async def threads_page(
    request: Request,
    status_value: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
) -> HTMLResponse:
    require_authenticated(request)
    thread_status = None
    if status_value:
        try:
            thread_status = ThreadStatus(status_value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid thread status filter.") from exc
    threads = await request.app.state.scheduler.thread_state.list_threads(
        limit=200,
        status=thread_status,
        search=search,
    )
    enriched_threads = [
        {
            "record": thread,
            "participants": _participants(request, thread.participants_json),
        }
        for thread in threads
    ]
    return _render(
        request,
        "admin/threads.html",
        threads=enriched_threads,
        search=search or "",
        selected_status=status_value or "",
        statuses=[status.value for status in ThreadStatus],
    )


@router.get("/threads/{thread_id}", response_class=HTMLResponse)
async def thread_detail(request: Request, thread_id: str) -> HTMLResponse:
    require_authenticated(request)
    thread_state = request.app.state.scheduler.thread_state
    thread = await thread_state.get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found.")
    proposals = await thread_state.list_proposals(thread_id)
    pending_approvals = await thread_state.list_pending_email_approvals_by_thread(thread_id)
    bound_event_ids = await thread_state.list_thread_calendar_event_ids(thread_id)
    return _render(
        request,
        "admin/thread_detail.html",
        thread=thread,
        participants=_participants(request, thread.participants_json),
        proposals=proposals,
        pending_approvals=pending_approvals,
        bound_event_ids=bound_event_ids,
    )


@router.get("/pending-approvals", response_class=HTMLResponse)
async def pending_approvals_page(request: Request) -> HTMLResponse:
    require_authenticated(request)
    approvals = await request.app.state.scheduler.thread_state.list_all_pending_email_approvals()
    return _render(request, "admin/pending_approvals.html", approvals=approvals)


@router.post("/actions/trust-sender")
async def trust_sender_action(
    request: Request,
    sender: str = Form(...),
    redirect_to: str = Form("/admin/pending-approvals"),
    csrf_token: str = Form(...),
) -> Response:
    require_authenticated(request)
    validate_csrf(request, csrf_token)
    await request.app.state.scheduler.approve_sender(sender)
    set_flash(request, "success", f"Trusted sender: {sender}")
    return _redirect(_safe_redirect_target(redirect_to))


@router.post("/actions/reject-sender")
async def reject_sender_action(
    request: Request,
    sender: str = Form(...),
    redirect_to: str = Form("/admin/pending-approvals"),
    csrf_token: str = Form(...),
) -> Response:
    require_authenticated(request)
    validate_csrf(request, csrf_token)
    await request.app.state.scheduler.reject_sender(sender)
    set_flash(request, "success", f"Rejected sender: {sender}")
    return _redirect(_safe_redirect_target(redirect_to))


@router.post("/actions/trust-thread")
async def trust_thread_action(
    request: Request,
    thread_id: str = Form(...),
    redirect_to: str = Form("/admin/pending-approvals"),
    csrf_token: str = Form(...),
) -> Response:
    require_authenticated(request)
    validate_csrf(request, csrf_token)
    await request.app.state.scheduler.approve_thread(thread_id)
    set_flash(request, "success", f"Trusted thread: {thread_id}")
    return _redirect(_safe_redirect_target(redirect_to))


@router.post("/actions/reject-thread")
async def reject_thread_action(
    request: Request,
    thread_id: str = Form(...),
    redirect_to: str = Form("/admin/pending-approvals"),
    csrf_token: str = Form(...),
) -> Response:
    require_authenticated(request)
    validate_csrf(request, csrf_token)
    await request.app.state.scheduler.reject_thread(thread_id)
    set_flash(request, "success", f"Rejected thread: {thread_id}")
    return _redirect(_safe_redirect_target(redirect_to))


@router.get("/trusted-senders", response_class=HTMLResponse)
async def trusted_senders_page(request: Request) -> HTMLResponse:
    require_authenticated(request)
    settings = request.app.state.settings
    db_senders = await request.app.state.scheduler.thread_state.list_trusted_senders()
    return _render(
        request,
        "admin/trusted_senders.html",
        db_senders=db_senders,
        env_senders=sorted(settings.email_trusted_senders),
        env_domains=sorted(settings.email_trusted_domains),
    )


@router.get("/security-audit", response_class=HTMLResponse)
async def security_audit_page(
    request: Request,
    source: str | None = Query(default=None),
    action: str | None = Query(default=None),
    decision: str | None = Query(default=None),
) -> HTMLResponse:
    require_authenticated(request)
    audits = await request.app.state.scheduler.thread_state.list_security_audit_events(
        limit=250,
        source=source,
        action=action,
        decision=decision,
    )
    enriched_audits = [
        {
            "record": audit,
            "metadata_pretty": _pretty_json(audit.metadata_json),
        }
        for audit in audits
    ]
    return _render(
        request,
        "admin/security_audit.html",
        audits=enriched_audits,
        selected_source=source or "",
        selected_action=action or "",
        selected_decision=decision or "",
    )


@router.get("/dead-letters", response_class=HTMLResponse)
async def dead_letters_page(request: Request) -> HTMLResponse:
    require_authenticated(request)
    dead_letters = await request.app.state.scheduler.thread_state.list_dead_letters(limit=200)
    enriched_dead_letters = [
        {
            "record": dead_letter,
            "payload_pretty": _pretty_json(dead_letter.payload_json),
        }
        for dead_letter in dead_letters
    ]
    return _render(request, "admin/dead_letters.html", dead_letters=enriched_dead_letters)


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    require_authenticated(request)
    settings = request.app.state.settings
    config_summary = {
        "app_env": settings.app_env,
        "app_timezone": settings.app_timezone,
        "web_admin_enabled": settings.web_admin_enabled,
        "web_session_max_age_seconds": settings.web_session_max_age_seconds,
        "telegram_admin_chat_id": bool(settings.telegram_admin_chat_id),
        "telegram_allowed_chat_ids": sorted(settings.telegram_allowed_chat_ids),
        "telegram_allow_group_chats": settings.telegram_allow_group_chats,
        "email_trust_required": settings.email_require_trust_for_automation,
        "email_trusted_senders": sorted(settings.email_trusted_senders),
        "email_trusted_domains": sorted(settings.email_trusted_domains),
        "google_calendar_configured": bool(settings.google_refresh_token),
        "agentmail_configured": bool(settings.agentmail_api_key and settings.agentmail_webhook_secret),
        "anthropic_configured": bool(settings.anthropic_api_key),
        "redis_enabled": bool(settings.redis_url),
    }
    return _render(request, "admin/settings.html", config_summary=config_summary)


@router.get("/tools", response_class=HTMLResponse)
async def tools_page(request: Request) -> HTMLResponse:
    require_authenticated(request)
    return _render(request, "admin/tools.html", result_text=None, operator_prompt="")


@router.post("/tools/message", response_class=HTMLResponse)
async def tools_message_action(
    request: Request,
    operator_prompt: str = Form(...),
    csrf_token: str = Form(...),
) -> HTMLResponse:
    require_authenticated(request)
    validate_csrf(request, csrf_token)
    prompt = operator_prompt.strip()
    result_text = ""
    if prompt:
        scheduler = request.app.state.scheduler
        result_text = await scheduler.handle_browser_operator_message(prompt)
    return _render(request, "admin/tools.html", result_text=result_text, operator_prompt=prompt)
