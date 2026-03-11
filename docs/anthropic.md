# Anthropic Setup

The Claude integration powers the reasoning loop used for Telegram conversations and email scheduling decisions.

## What You Need

- an Anthropic account
- an API key with access to the selected model

## Steps

1. Sign in to the Anthropic Console.
2. Create or copy an API key.
3. Add it to `.env`:

```env
ANTHROPIC_API_KEY=your_key_here
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

## What The App Uses It For

The app creates an `AsyncAnthropic` client and uses tool-calling to:

- answer Telegram messages
- inspect inbound email context
- check availability
- reserve proposed slots
- send email replies
- create or update calendar events

## Verification

After the app is running:

1. Message your Telegram bot with a normal text prompt.
2. Confirm you receive a real response rather than the fallback message about Anthropic not being configured.

If you see a fallback response, re-check `ANTHROPIC_API_KEY` in `.env`.
