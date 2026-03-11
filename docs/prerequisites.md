# Prerequisites

This project is a Python service that combines:

- a FastAPI web server for AgentMail webhooks
- a Telegram bot running in long-polling mode
- Claude via the Anthropic API
- Google Calendar API access
- SQLite persistence
- optional Redis caching for active thread state

## Required Accounts And Services

Before configuring the app, make sure you have:

- an Anthropic API key
- a Telegram bot token from BotFather
- an AgentMail inbox, API key, and webhook secret
- a Google Cloud project with Calendar API enabled and OAuth client credentials

## Local Software

Install the following locally:

- Python 3.11 or newer
- `pip`
- Docker Desktop if you want to run via `docker compose`
- Redis if you want local caching outside Docker

## Network Requirements

Telegram works locally because the app uses long-polling.

AgentMail webhooks require a public HTTPS URL for:

- local development via a tunnel such as Cloudflare Tunnel or ngrok
- deployment on a VPS or hosted container with a public domain

## Suggested Setup Order

1. Copy `.env.example` to `.env`.
2. Configure Anthropic.
3. Configure Telegram.
4. Configure AgentMail.
5. Configure Google Calendar.
6. Start the service and verify `/health`.
7. Send a Telegram message to the bot.
8. Send a test AgentMail webhook or real inbound email.
