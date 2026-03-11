from app.config import Settings
from app.integrations.telegram import TelegramBotService


async def _noop(_message):
    return None


def test_settings_falls_back_to_admin_chat_for_allowlist():
    settings = Settings(TELEGRAM_ADMIN_CHAT_ID="123456789")

    assert settings.telegram_allowed_chat_ids == {"123456789"}


def test_settings_parses_explicit_telegram_allowlist():
    settings = Settings(
        TELEGRAM_ADMIN_CHAT_ID="123456789",
        TELEGRAM_ALLOWED_CHAT_IDS="123456789, 987654321 , ,555",
    )

    assert settings.telegram_allowed_chat_ids == {"123456789", "987654321", "555"}


def test_telegram_service_only_allows_private_authorized_chats_by_default():
    service = TelegramBotService(
        token=None,
        default_chat_id="123456789",
        on_message=_noop,
        allowed_chat_ids={"123456789"},
    )

    assert service.is_inbound_chat_allowed("123456789", "private")
    assert not service.is_inbound_chat_allowed("999999999", "private")
    assert not service.is_inbound_chat_allowed("123456789", "group")


def test_telegram_service_can_allow_groups_when_enabled():
    service = TelegramBotService(
        token=None,
        default_chat_id="123456789",
        on_message=_noop,
        allowed_chat_ids={"123456789"},
        allow_group_chats=True,
    )

    assert service.is_inbound_chat_allowed("123456789", "group")
