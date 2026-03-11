# Persistent Agent Daemon

An always-on personal assistant daemon that lives across chat, email, and calendar.

This project is built around a simple idea: your assistant should be reachable where work actually happens. Instead of living in a single UI, it can talk to you in Telegram, react to inbound email threads through AgentMail, inspect your Google Calendar, and coordinate scheduling with real tool use instead of brittle text parsing.

The result is a small Python service with a practical bias: async, container-friendly, easy to run locally, and designed for autonomous but inspectable actions.

## Why This Exists

Modern assistants are great at reasoning, but they are often disconnected from the channels where logistics happen. Meeting coordination is a perfect example:

- someone emails you asking to meet
- you want your assistant to understand the thread
- it should check your availability
- propose real open times
- book the event when confirmed
- and notify you in Telegram when it is done

That is the spirit of this project: a useful, persistent, operator-friendly assistant with enough memory, guardrails, and integrations to handle real-world coordination.

## What It Does

- runs a FastAPI daemon for inbound webhooks and health checks
- listens for Telegram messages via long-polling
- receives inbound email events from AgentMail
- uses Claude with strict tool schemas for action selection
- checks Google Calendar availability and manages events
- stores durable thread state in SQLite with optional Redis caching
- tracks multi-turn scheduling workflows across email threads

## Documentation

For setup, configuration, and run guides, start here:

- [Docs Home](docs/README.md)

Direct links:

- [Prerequisites](docs/prerequisites.md)
- [Environment Configuration](docs/environment.md)
- [Anthropic Setup](docs/anthropic.md)
- [Telegram Setup](docs/telegram.md)
- [AgentMail Setup](docs/agentmail.md)
- [Google Calendar Setup](docs/google-calendar.md)
- [Running And Verification](docs/running.md)

## Architecture At A Glance

```text
Telegram -> daemon -> Claude tool loop
Email -> AgentMail webhook -> daemon -> Claude tool loop
Claude tools -> calendar, email reply, Telegram notify, thread state
```

The daemon is intentionally small and composable:

- `FastAPI` handles health checks and AgentMail webhook intake
- `python-telegram-bot` handles direct operator conversation
- `Anthropic` powers tool-based reasoning
- `Google Calendar` provides live scheduling context
- `SQLite` keeps durable thread and event history
- `Redis` optionally speeds up active thread state access

## Quick Start

1. Copy `.env.example` to `.env`.
2. Follow the guides in [Docs Home](docs/README.md) and fill in the required credentials.
3. Install dependencies:

```bash
pip install -e .[dev]
```

4. Start the app:

```bash
uvicorn app.main:app --reload
```

5. Or run with Docker:

```bash
docker compose up --build
```

6. Verify the service at `GET /health`.

## Configuration Overview

The daemon reads configuration from `.env`.

- App/runtime: `APP_ENV`, `APP_TIMEZONE`, `HOST`, `PORT`, `LOG_LEVEL`
- Anthropic: `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`
- Telegram: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID`
- AgentMail: `AGENTMAIL_API_KEY`, `AGENTMAIL_API_BASE`, `AGENTMAIL_WEBHOOK_SECRET`, `AGENTMAIL_INBOX_ADDRESS`
- Google Calendar: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `GOOGLE_CALENDAR_ID`
- Persistence: `REDIS_URL`, `SQLITE_PATH`

Full setup details live in [docs/README.md](docs/README.md).

## Endpoints

- `GET /health`
- `POST /webhooks/agentmail`

## Project Layout

- `app/main.py`: app bootstrap, lifecycle wiring, and HTTP endpoints
- `app/integrations/`: Telegram, AgentMail, and Google Calendar adapters
- `app/llm/claude_agent.py`: Claude tool-use orchestration
- `app/services/`: scheduling logic, reliability helpers, and thread state
- `app/db/`: SQLite models and persistence helpers
- `app/schemas/`: Pydantic schemas for payloads and tool contracts
- `docs/`: setup and operating guides
- `tests/`: unit and integration-oriented coverage

## Current Status

The core scaffold is in place and ready for configuration:

- local Telegram interaction is supported
- AgentMail webhook ingestion is wired
- Google Calendar integration is implemented
- SQLite persistence and dead-letter storage are in place
- the docs walk through what to configure next

Depending on your AgentMail account or API version, you may need to adjust the outbound reply endpoint or payload shape in `app/integrations/agentmail.py`.
