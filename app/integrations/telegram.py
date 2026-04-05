from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from app.schemas.telegram import TelegramInboundMessage

logger = logging.getLogger(__name__)

TelegramCallback = Callable[[TelegramInboundMessage], Awaitable[str | None]]
TelegramAdminCallback = Callable[[str], Awaitable[str | None]]
TelegramSecurityCallback = Callable[[str, str], Awaitable[None]]


class TelegramBotService:
    def __init__(
        self,
        token: str | None,
        default_chat_id: str | None,
        on_message: TelegramCallback,
        allowed_chat_ids: set[str] | None = None,
        allow_group_chats: bool = False,
        on_trust_sender: TelegramAdminCallback | None = None,
        on_reject_sender: TelegramAdminCallback | None = None,
        on_trust_thread: TelegramAdminCallback | None = None,
        on_reject_thread: TelegramAdminCallback | None = None,
        on_unauthorized_access: TelegramSecurityCallback | None = None,
    ):
        self.token = token
        self.default_chat_id = default_chat_id
        self.on_message = on_message
        self.allowed_chat_ids = {chat_id.strip() for chat_id in (allowed_chat_ids or set()) if chat_id.strip()}
        self.allow_group_chats = allow_group_chats
        self.on_trust_sender = on_trust_sender
        self.on_reject_sender = on_reject_sender
        self.on_trust_thread = on_trust_thread
        self.on_reject_thread = on_reject_thread
        self.on_unauthorized_access = on_unauthorized_access
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
        self.application.add_handler(CommandHandler("whoami", self._handle_whoami))
        self.application.add_handler(CommandHandler("trust_sender", self._handle_trust_sender))
        self.application.add_handler(CommandHandler("reject_sender", self._handle_reject_sender))
        self.application.add_handler(CommandHandler("trust_thread", self._handle_trust_thread))
        self.application.add_handler(CommandHandler("reject_thread", self._handle_reject_thread))
        self.application.add_handler(CallbackQueryHandler(self._handle_callback_action))
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

    async def send_message(
        self,
        text: str,
        chat_id: str | None = None,
        buttons: list[list[dict[str, str]]] | None = None,
    ) -> None:
        if not self.application:
            logger.info("Telegram send skipped because application is not started: %s", text)
            return
        target_chat = chat_id or self.default_chat_id
        if not target_chat:
            logger.warning("Telegram chat_id missing; message dropped.")
            return
        reply_markup = self._build_reply_markup(buttons)
        await self.application.bot.send_message(chat_id=target_chat, text=text, reply_markup=reply_markup)

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize_update(update):
            return
        if update.effective_message:
            await update.effective_message.reply_text("🤖 MyPA is online and ready.")

    async def _handle_whoami(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize_update(update):
            return
        if not update.effective_message or not update.effective_chat:
            return
        await update.effective_message.reply_text(
            f"🆔 Chat ID: {update.effective_chat.id}\n"
            f"💬 Chat type: {update.effective_chat.type}"
        )

    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize_update(update):
            return
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

    async def _handle_trust_sender(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._handle_sender_command(update, context, self.on_trust_sender, "trust_sender")

    async def _handle_reject_sender(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._handle_sender_command(update, context, self.on_reject_sender, "reject_sender")

    async def _handle_trust_thread(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._handle_sender_command(update, context, self.on_trust_thread, "trust_thread")

    async def _handle_reject_thread(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._handle_sender_command(update, context, self.on_reject_thread, "reject_thread")

    async def _handle_sender_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        callback: TelegramAdminCallback | None,
        command_name: str,
    ) -> None:
        if not await self._authorize_update(update):
            return
        if not update.effective_message:
            return
        sender = " ".join(context.args).strip()
        if not sender:
            await update.effective_message.reply_text(f"ℹ️ Usage: /{command_name} sender@example.com")
            return
        if not callback:
            await update.effective_message.reply_text("⚠️ This command is not configured.")
            return
        reply = await callback(sender)
        if reply:
            await update.effective_message.reply_text(reply)

    async def _handle_callback_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize_update(update):
            return
        query = update.callback_query
        if not query or not query.data:
            return
        await query.answer()
        command_name, _, argument = query.data.partition("|")
        callback = self._resolve_action_callback(command_name)
        if not callback:
            await query.edit_message_reply_markup(reply_markup=None)
            if query.message:
                await query.message.reply_text("This action is not configured.")
            return
        if not argument.strip():
            await query.edit_message_reply_markup(reply_markup=None)
            if query.message:
                await query.message.reply_text(f"Missing action value for {command_name}.")
            return
        reply = await callback(argument.strip())
        await query.edit_message_reply_markup(reply_markup=None)
        if query.message and reply:
            await query.message.reply_text(reply)

    def _resolve_action_callback(self, command_name: str) -> TelegramAdminCallback | None:
        callbacks = {
            "trust_sender": self.on_trust_sender,
            "reject_sender": self.on_reject_sender,
            "trust_thread": self.on_trust_thread,
            "reject_thread": self.on_reject_thread,
        }
        return callbacks.get(command_name)

    @staticmethod
    def _build_reply_markup(buttons: list[list[dict[str, str]]] | None) -> InlineKeyboardMarkup | None:
        if not buttons:
            return None
        keyboard = []
        for row in buttons:
            keyboard_row = []
            for button in row:
                text = button.get("text", "").strip()
                callback_data = button.get("callback_data", "").strip()
                if not text or not callback_data:
                    continue
                keyboard_row.append(InlineKeyboardButton(text=text, callback_data=callback_data))
            if keyboard_row:
                keyboard.append(keyboard_row)
        if not keyboard:
            return None
        return InlineKeyboardMarkup(keyboard)

    def is_inbound_chat_allowed(self, chat_id: str, chat_type: str) -> bool:
        if chat_type != "private" and not self.allow_group_chats:
            return False
        if not self.allowed_chat_ids:
            return True
        return chat_id in self.allowed_chat_ids

    async def _authorize_update(self, update: Update) -> bool:
        if not update.effective_chat:
            return False
        chat_id = str(update.effective_chat.id)
        chat_type = update.effective_chat.type
        if self.is_inbound_chat_allowed(chat_id, chat_type):
            return True
        logger.warning("Unauthorized Telegram chat blocked: id=%s type=%s", chat_id, chat_type)
        if self.on_unauthorized_access:
            await self.on_unauthorized_access(chat_id, chat_type)
        if update.effective_message and chat_type == "private":
            await update.effective_message.reply_text("⛔ This bot is not authorized for this chat.")
        return False
