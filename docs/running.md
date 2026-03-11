# Running And Verification

This guide covers local startup, Docker startup, health checks, and basic end-to-end verification.

## Local Run

Install dependencies:

```bash
pip install -e .[dev]
```

Start the app:

```bash
uvicorn app.main:app --reload
```

The default local server is:

```text
http://127.0.0.1:8000
```

## Docker Run

Create `.env`, then run:

```bash
docker compose up --build
```

This starts:

- the FastAPI daemon
- Redis

SQLite data is stored under `data/`.

## Health Check

Call:

```text
GET /health
```

Expected fields include:

- `status`
- `environment`
- `telegram_enabled`
- `anthropic_configured`
- `google_calendar_configured`
- `redis_status`

## Recommended First Boot Checklist

1. Start the app.
2. Open `http://127.0.0.1:8000/health`.
3. Confirm `status` is `ok`.
4. Confirm Redis is `ok` if you configured it, or `disabled` if you intentionally left it blank.
5. If `WEB_ADMIN_PASSWORD` is configured, open `http://127.0.0.1:8000/admin/login` and confirm the admin UI loads.
6. Send `/start` to the Telegram bot.
7. Send a regular Telegram message and confirm you receive a Claude-backed reply.
8. If using AgentMail locally, start your tunnel and update the webhook URL in AgentMail.
9. Send a test inbound email to the AgentMail inbox.

## Suggested End-To-End Test

1. Send a Telegram message like `Am I free Thursday afternoon?`
2. Confirm the bot replies.
3. Send an email thread into the AgentMail inbox that asks to meet.
4. Confirm the webhook hits `/webhooks/agentmail`.
5. Confirm the app checks availability and, when appropriate, proposes times or creates an event.
6. Confirm Telegram receives a notification when a meeting is confirmed.
7. If web admin is enabled, open `/admin/tools`, submit a simple operator request, and confirm the browser renders the response.

## Troubleshooting

- App starts but Telegram is silent: check `TELEGRAM_BOT_TOKEN`
- Health check shows Google not configured: check `GOOGLE_REFRESH_TOKEN`
- AgentMail webhook returns `401`: check `AGENTMAIL_WEBHOOK_SECRET`
- AgentMail webhook returns `500`: inspect logs and the dead-letter entries in the SQLite database
- Calendar actions are simulated: one or more Google credentials are blank
- Email replies are simulated: `AGENTMAIL_API_KEY` is blank
- `/admin/login` returns `404`: set `WEB_ADMIN_PASSWORD`
- Admin pages keep logging you out: set a stable `WEB_SESSION_SECRET` and make sure the app is running behind HTTPS in production
