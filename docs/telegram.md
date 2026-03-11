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

The app can reply directly to the chat that messages the bot, but `TELEGRAM_ADMIN_CHAT_ID` is also used for proactive notifications and, by default, inbound authorization.

To get your chat ID:

1. Start the app.
2. Open a chat with your bot and send `/start`.
3. Send a normal message to the bot.
4. Inspect logs or temporarily call the Telegram Bot API `getUpdates` method if you need the numeric chat ID.

Then store it in `.env`:

```env
TELEGRAM_ADMIN_CHAT_ID=123456789
```

If you want to authorize more than one inbound chat, add a comma-separated allowlist:

```env
TELEGRAM_ALLOWED_CHAT_IDS=123456789,987654321
```

By default, the bot only accepts inbound traffic from private chats. To allow group chats too:

```env
TELEGRAM_ALLOW_GROUP_CHATS=true
```

## How It Runs

Telegram uses long-polling in this project, so it does not need a public webhook URL during development.

## Verification

1. Start the app.
2. Send `/start` to the bot.
3. Confirm the bot replies with `Persistent agent daemon is online.`
4. Send a normal message.
5. Confirm the bot responds through the Claude loop.

## Admin Approval Commands

When email trust enforcement is enabled and an untrusted sender emails the agent, the bot sends the admin a Telegram message with approval instructions.

- `/trust_sender sender@example.com`: trust the sender going forward and process any queued blocked emails from that sender
- `/reject_sender sender@example.com`: reject and clear queued blocked emails from that sender

## Common Issues

- No responses at all: check `TELEGRAM_BOT_TOKEN`
- Replies work, but notifications do not: check `TELEGRAM_ADMIN_CHAT_ID`
- The bot says it is not authorized for this chat: add that chat ID to `TELEGRAM_ALLOWED_CHAT_IDS` or make it the `TELEGRAM_ADMIN_CHAT_ID`
- The bot works in direct chat but ignores groups: this is expected unless `TELEGRAM_ALLOW_GROUP_CHATS=true`
- Bot starts but nothing arrives: make sure you initiated a conversation with the bot first
