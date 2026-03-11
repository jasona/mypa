# AgentMail Setup

AgentMail provides the inbox identity and webhook delivery for inbound email threads.

## What You Need

- an AgentMail inbox address
- an AgentMail API key for outbound replies
- a webhook signing secret
- a public HTTPS URL that AgentMail can call

## Environment Variables

Fill in:

```env
AGENTMAIL_API_KEY=your_agentmail_api_key
AGENTMAIL_API_BASE=https://api.agentmail.to
AGENTMAIL_WEBHOOK_SECRET=your_webhook_secret
AGENTMAIL_INBOX_ADDRESS=assistant@yourdomain.agentmail.to
```

## Webhook Target

Configure AgentMail to send inbound email events to:

```text
https://your-public-host/webhooks/agentmail
```

For local development, expose your app with a tunnel and use that public URL instead of `localhost`.

## Request Validation

The app expects the webhook signature in:

```text
X-AgentMail-Signature
```

The request body is validated against `AGENTMAIL_WEBHOOK_SECRET`. If the signature is wrong, the app returns `401`.

## Expected Payload Shape

The current implementation expects the webhook body to contain, directly or inside `message`:

- `event_id`
- `thread_id`
- `message_id`
- `subject`
- `from`
- `to`
- `cc`
- `body_text` or `message.text`
- `received_at`

## Important Note

The outbound reply implementation currently posts to:

```text
POST {AGENTMAIL_API_BASE}/v1/messages/reply
```

with a JSON body containing:

- `thread_id`
- `subject`
- `text`
- `to`
- `cc`
- `in_reply_to`

If your actual AgentMail account or API version uses a different endpoint or payload shape, update `app/integrations/agentmail.py` accordingly.

## Verification

1. Start the app.
2. Confirm `GET /health` returns `status: ok`.
3. Send a real or test email into the AgentMail inbox.
4. Confirm AgentMail successfully posts to `/webhooks/agentmail`.
5. Check the app logs for processing results.
6. If processing fails, inspect the SQLite dead-letter table in `SQLITE_PATH`.
