# Telegram Setup

Telegram is the primary operator interface for direct conversation and failure notifications.

## Create The Bot

1. Open Telegram and message `@BotFather`.
2. Run `/newbot`.
3. Choose a bot name and username.
4. Copy the bot token BotFather returns.

Add it to `.env`:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
```

## Get Your Chat ID

The app can reply directly to the chat that messages the bot, but `TELEGRAM_ADMIN_CHAT_ID` is also used for proactive notifications.

To get your chat ID:

1. Start the app.
2. Open a chat with your bot and send `/start`.
3. Send a normal message to the bot.
4. Inspect logs or temporarily call the Telegram Bot API `getUpdates` method if you need the numeric chat ID.

Then store it in `.env`:

```env
TELEGRAM_ADMIN_CHAT_ID=123456789
```

## How It Runs

Telegram uses long-polling in this project, so it does not need a public webhook URL during development.

## Verification

1. Start the app.
2. Send `/start` to the bot.
3. Confirm the bot replies with `Persistent agent daemon is online.`
4. Send a normal message.
5. Confirm the bot responds through the Claude loop.

## Common Issues

- No responses at all: check `TELEGRAM_BOT_TOKEN`
- Replies work, but notifications do not: check `TELEGRAM_ADMIN_CHAT_ID`
- Bot starts but nothing arrives: make sure you initiated a conversation with the bot first
