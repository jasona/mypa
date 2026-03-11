# Documentation

This folder contains the setup and operating guides for the Persistent Agent Daemon.

If you are starting from scratch, use the docs in this order:

1. [Prerequisites](prerequisites.md)
2. [Environment Configuration](environment.md)
3. [Anthropic Setup](anthropic.md)
4. [Telegram Setup](telegram.md)
5. [AgentMail Setup](agentmail.md)
6. [Google Calendar Setup](google-calendar.md)
7. [Running And Verification](running.md)
8. [Security Hardening Plan](security-hardening.md)

## What Each Guide Covers

- [Prerequisites](prerequisites.md): required accounts, local software, and public webhook expectations
- [Environment Configuration](environment.md): every `.env` variable and what happens if it is missing
- [Anthropic Setup](anthropic.md): API key setup for Claude reasoning
- [Telegram Setup](telegram.md): bot creation, token setup, and admin chat ID
- [AgentMail Setup](agentmail.md): inbox, webhook, signature validation, and outbound reply notes
- [Google Calendar Setup](google-calendar.md): OAuth credentials, refresh token, and calendar scopes
- [Running And Verification](running.md): local run, Docker run, health checks, and end-to-end smoke tests
- [Security Hardening Plan](security-hardening.md): phased implementation plan for abuse prevention and production hardening

## Recommended First Success Path

If your goal is to get to a working local demo quickly:

1. Configure `.env`
2. Add Anthropic and Telegram credentials
3. Start the app
4. Confirm Telegram conversation works
5. Add Google Calendar credentials
6. Test availability queries
7. Add AgentMail and a public webhook URL
8. Test an inbound scheduling email
