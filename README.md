# MyPA 🤖📅📨

An always-on personal assistant that lives in Telegram, email, and your calendar.

`MyPA` is built for real-world coordination work: understanding inbound email threads, checking availability, proposing times, booking meetings, notifying you in Telegram, and giving you a browser-based admin console to monitor what it is doing.

It is intentionally practical: small, async, container-friendly, operator-visible, and guarded by trust controls instead of blind autonomy.

## Why MyPA Exists

Most assistants are trapped inside a chat box. Actual scheduling work is not.

It happens in:

- 📱 Telegram when you want quick operator control
- 📨 Email threads when other people are coordinating with you
- 📅 Google Calendar when availability and confirmed meetings matter

MyPA connects those surfaces with a Claude-powered tool loop, durable thread state, and explicit security guardrails.

## What MyPA Can Do

- 🤖 Answer and act on Telegram requests
- 📨 Receive AgentMail webhooks and reason over inbound email threads
- ✉️ Reply to existing email threads and initiate new outbound emails when policy allows
- 📅 Check Google Calendar availability and create, update, or delete events
- 🧠 Use strict Claude tool schemas instead of brittle free-form parsing
- 🗂️ Persist thread state, approvals, proposals, dead letters, and audit events in SQLite
- ⚡ Optionally use Redis as a cache for active thread state
- 🔐 Enforce trusted sender/domain controls, Telegram allowlisting, and calendar mutation boundaries
- 🌐 Expose a password-protected web admin console for operations and review

## Key Features

### Operator Surfaces

- 📱 Telegram long-polling bot for day-to-day control
- 🌐 Server-rendered `/admin` console for browser-based monitoring and admin actions

### Scheduling Workflow

- 📨 Understands inbound scheduling threads
- 📅 Checks live availability
- ⏱️ Reserves candidate slots
- ✉️ Sends scheduling responses through AgentMail
- ✅ Creates confirmed calendar events
- 🔔 Sends Telegram notifications when important things happen

### Security And Guardrails

- 🔒 Telegram inbound allowlisting
- 🧾 Trusted sender and trusted domain controls for email automation
- 🧵 Thread-level approval flow for continued automation on approved threads
- 🚫 Restrictions on untrusted outbound email initiation
- 🗓️ Bound-event protection for external calendar mutations
- 🧹 Redacted/truncated dead-letter storage and minimized untrusted context to the LLM
- 🚨 Security audit logging and operator alerts

## Architecture

```text
Telegram -> MyPA -> Claude tool loop
AgentMail webhook -> MyPA -> Claude tool loop
Claude tools -> AgentMail / Google Calendar / Telegram / SQLite / Redis
Browser admin -> FastAPI /admin -> scheduler + SQLite read models
```

Core building blocks:

- `FastAPI` for health checks, AgentMail webhooks, and the admin UI
- `python-telegram-bot` for Telegram messaging
- `Anthropic` for tool-driven reasoning
- `Google Calendar API` for availability and event management
- `SQLite` for durable operational state
- `Redis` for optional active-thread caching

## Quick Start 🚀

1. Copy `.env.example` to `.env`.
2. Follow the setup docs in [docs/README.md](docs/README.md).
3. Install dependencies:

```bash
pip install -e .[dev]
```

4. Run locally:

```bash
uvicorn app.main:app --reload
```

5. Or run with Docker:

```bash
docker compose up --build
```

6. Verify:

- `GET /health`
- `GET /admin/login` if `WEB_ADMIN_PASSWORD` is configured

## Configuration Overview

MyPA reads configuration from `.env`.

- ⚙️ Runtime: `APP_ENV`, `APP_TIMEZONE`, `HOST`, `PORT`, `LOG_LEVEL`
- 🧠 Anthropic: `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`
- 📱 Telegram: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID`, `TELEGRAM_ALLOWED_CHAT_IDS`, `TELEGRAM_ALLOW_GROUP_CHATS`
- 📨 AgentMail: `AGENTMAIL_API_KEY`, `AGENTMAIL_API_BASE`, `AGENTMAIL_WEBHOOK_SECRET`, `AGENTMAIL_INBOX_ADDRESS`
- 📅 Google Calendar: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `GOOGLE_CALENDAR_ID`, `WORKSPACE_EMAIL_DOMAIN`, `CALENDAR_ALIAS_MAP_JSON`
- 🔐 Email trust: `EMAIL_TRUSTED_SENDERS`, `EMAIL_TRUSTED_DOMAINS`, `EMAIL_REQUIRE_TRUST_FOR_AUTOMATION`
- 🌐 Web admin: `WEB_ADMIN_PASSWORD`, `WEB_SESSION_SECRET`, `WEB_SESSION_MAX_AGE_SECONDS`
- 💾 Persistence: `REDIS_URL`, `SQLITE_PATH`

Full setup and environment details live in [docs/environment.md](docs/environment.md).

## Documentation 📚

Start here:

- [Docs Home](docs/README.md)

Setup and operations guides:

- [Prerequisites](docs/prerequisites.md)
- [Environment Configuration](docs/environment.md)
- [Anthropic Setup](docs/anthropic.md)
- [Telegram Setup](docs/telegram.md)
- [AgentMail Setup](docs/agentmail.md)
- [Google Calendar Setup](docs/google-calendar.md)
- [Web Admin](docs/web-admin.md)
- [Running And Verification](docs/running.md)
- [Security Hardening Plan](docs/security-hardening.md)

## HTTP Endpoints

- `GET /health`
- `POST /webhooks/agentmail`
- `GET /admin/login`
- `GET /admin`

## Project Layout

- `app/main.py`: app bootstrap, lifecycle wiring, and HTTP routes
- `app/integrations/`: Telegram, AgentMail, and Google Calendar integrations
- `app/llm/claude_agent.py`: Claude tool-use orchestration
- `app/services/`: scheduling, reliability, and thread-state logic
- `app/db/`: SQLite models and persistence helpers
- `app/web/`: web auth and admin routes
- `templates/admin/`: server-rendered admin templates
- `docs/`: setup, deployment, and operations guides
- `tests/`: automated coverage

## Current State

MyPA is no longer just a scaffold. The current project includes:

- ✅ Telegram operator workflow
- ✅ AgentMail inbound webhook handling
- ✅ Outbound email reply and send support
- ✅ Google Calendar reads and mutations
- ✅ SQLite-backed thread state, approvals, audits, and dead letters
- ✅ Browser admin console
- ✅ Security controls around trust, replay, and mutation boundaries

## Philosophy

MyPA is meant to be helpful, autonomous where appropriate, and inspectable when it matters.

The goal is not to create a mysterious black box assistant.

The goal is to create a personal operations agent you can actually run, monitor, trust, and improve.
