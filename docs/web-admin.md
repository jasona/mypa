# Web Admin

MyPA now includes a lightweight server-rendered admin console under `/admin`.

It is designed for single-operator use and complements the Telegram admin workflow rather than replacing it.

## Required Environment Variables

- `WEB_ADMIN_PASSWORD`: the password used on `/admin/login`
- `WEB_SESSION_SECRET`: secret used to sign the session cookie. Set this explicitly in production.
- `WEB_SESSION_MAX_AGE_SECONDS`: optional session lifetime, default `43200` seconds

## What The Admin UI Exposes

- dashboard counts and recent activity
- thread list and thread detail views
- pending email approval queue
- trusted senders from SQLite plus env-based allowlists
- security audit events
- dead-letter records with redacted payloads
- operator tools page to submit the same kind of request you would send via Telegram

## Security Notes

- The admin UI is disabled unless `WEB_ADMIN_PASSWORD` is set.
- All admin pages and POST actions require a signed session cookie.
- All admin POST forms include a CSRF token.
- The settings page intentionally shows only redacted or boolean configuration state.
- Dead-letter payloads remain redacted and truncated using the existing dead-letter safeguards.

## Recommended Production Setup

1. Set a strong `WEB_ADMIN_PASSWORD`.
2. Set a long random `WEB_SESSION_SECRET`.
3. Run behind HTTPS.
4. Keep the admin UI limited to operators you trust with full Telegram admin powers.

## Basic Verification

1. Start the app.
2. Open `/admin/login`.
3. Sign in with `WEB_ADMIN_PASSWORD`.
4. Confirm the dashboard loads.
5. Visit `/admin/pending-approvals` and `/admin/security-audit`.
6. Use `/admin/tools` to send a simple operator request and confirm the response renders in the browser.
