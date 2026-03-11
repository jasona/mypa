# Environment Configuration

The app loads configuration from `.env` using `pydantic-settings`.

Start by copying:

```bash
copy .env.example .env
```

Then fill in the variables below.

## App And Scheduling

- `APP_ENV`: environment label such as `development` or `production`
- `APP_TIMEZONE`: default timezone for scheduling, for example `America/New_York`
- `WORKING_HOURS_START`: start of normal availability, such as `09:00`
- `WORKING_HOURS_END`: end of normal availability, such as `17:00`
- `MEETING_BUFFER_MINUTES`: buffer between meetings
- `DEFAULT_MEETING_DURATION_MINUTES`: default duration used by scheduling flows

## Web Server

- `HOST`: interface for FastAPI, usually `0.0.0.0`
- `PORT`: server port, default `8000`
- `LOG_LEVEL`: usually `INFO` during normal setup

## Anthropic

- `ANTHROPIC_API_KEY`: required for Claude reasoning
- `ANTHROPIC_MODEL`: default is `claude-sonnet-4-20250514`

If `ANTHROPIC_API_KEY` is blank, the service still starts, but autonomous reasoning is disabled.

## Telegram

- `TELEGRAM_BOT_TOKEN`: required to enable polling
- `TELEGRAM_ADMIN_CHAT_ID`: optional but strongly recommended for operator notifications
- `TELEGRAM_ALLOWED_CHAT_IDS`: optional comma-separated allowlist for inbound operator chats. If left blank, the app falls back to `TELEGRAM_ADMIN_CHAT_ID` for inbound authorization when that value is set.
- `TELEGRAM_ALLOW_GROUP_CHATS`: defaults to `false`. Keep this disabled unless you explicitly want the bot to operate in group chats.

If `TELEGRAM_BOT_TOKEN` is blank, Telegram polling is disabled.

## AgentMail

- `AGENTMAIL_API_KEY`: used for outbound replies
- `AGENTMAIL_API_BASE`: defaults to `https://api.agentmail.to`
- `AGENTMAIL_WEBHOOK_SECRET`: used to validate the `X-AgentMail-Signature` header
- `AGENTMAIL_INBOX_ADDRESS`: your agent inbox address

If `AGENTMAIL_API_KEY` is blank, outbound email replies are simulated.

## Google Calendar

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REFRESH_TOKEN`
- `GOOGLE_CALENDAR_ID`: usually `primary`
- `WORKSPACE_EMAIL_DOMAIN`: optional fallback domain for resolving coworker names like `Jane Smith` to `jane.smith@yourdomain.com`
- `CALENDAR_ALIAS_MAP_JSON`: optional JSON map for coworker aliases, for example `{"jane":"jane@yourdomain.com","jane smith":"jane@yourdomain.com"}`

If the Google credentials are missing, calendar reads and writes fall back to simulated behavior.

## Persistence

- `REDIS_URL`: optional Redis cache for active thread state, for example `redis://localhost:6379/0`
- `SQLITE_PATH`: local SQLite database path, default `data/agent.db`

Redis is used only as a performance/cache layer for active thread state. If `REDIS_URL` is blank, or Redis is unavailable at runtime, the app falls back to SQLite-only operation.

## Recommended Minimum `.env`

For a functional local setup, fill in at least:

- `ANTHROPIC_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ADMIN_CHAT_ID`
- `AGENTMAIL_WEBHOOK_SECRET`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REFRESH_TOKEN`

For full email reply support, also fill in:

- `AGENTMAIL_API_KEY`
- `AGENTMAIL_INBOX_ADDRESS`
