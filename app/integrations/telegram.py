from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from app.schemas.telegram import TelegramInboundMessage

logger = logging.getLogger(__name__)

TelegramCallback = Callable[[TelegramInboundMessage], Awaitable[str | None]]


class TelegramBotService:
    def __init__(self, token: str | None, default_chat_id: str | None, on_message: TelegramCallback):
        self.token = token
        self.default_chat_id = default_chat_id
        self.on_message = on_message
        self.application: Application | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    async def start(self) -> None:
        if not self.enabled:
            logger.warning("Telegram bot token is not configured; Telegram polling disabled.")
            return

        self.application = ApplicationBuilder().token(self.token).build()
        self.application.add_handler(CommandHandler("start", self._handle_start))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text))
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        logger.info("Telegram polling started.")

    async def stop(self) -> None:
        if not self.application:
            return
        if self.application.updater:
            await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
        logger.info("Telegram polling stopped.")

    async def send_message(self, text: str, chat_id: str | None = None) -> None:
        if not self.application:
            logger.info("Telegram send skipped because application is not started: %s", text)
            return
        target_chat = chat_id or self.default_chat_id
        if not target_chat:
            logger.warning("Telegram chat_id missing; message dropped.")
            return
        await self.application.bot.send_message(chat_id=target_chat, text=text)

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message:
            await update.effective_message.reply_text("Persistent agent daemon is online.")

    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not update.effective_chat:
            return
        inbound = TelegramInboundMessage(
            chat_id=str(update.effective_chat.id),
            text=update.effective_message.text or "",
            message_id=str(update.effective_message.message_id),
            sent_at=datetime.now(timezone.utc),
        )
        reply = await self.on_message(inbound)
        if reply:
            await update.effective_message.reply_text(reply)
