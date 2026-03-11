import json
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    app_timezone: str = Field(default="America/New_York", alias="APP_TIMEZONE")
    working_hours_start: str = Field(default="09:00", alias="WORKING_HOURS_START")
    working_hours_end: str = Field(default="17:00", alias="WORKING_HOURS_END")
    meeting_buffer_minutes: int = Field(default=15, alias="MEETING_BUFFER_MINUTES")
    default_meeting_duration_minutes: int = Field(default=30, alias="DEFAULT_MEETING_DURATION_MINUTES")

    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-sonnet-4-20250514", alias="ANTHROPIC_MODEL")

    telegram_bot_token: str | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_admin_chat_id: str | None = Field(default=None, alias="TELEGRAM_ADMIN_CHAT_ID")
    telegram_allowed_chat_ids_raw: str | None = Field(default=None, alias="TELEGRAM_ALLOWED_CHAT_IDS")
    telegram_allow_group_chats: bool = Field(default=False, alias="TELEGRAM_ALLOW_GROUP_CHATS")

    agentmail_api_key: str | None = Field(default=None, alias="AGENTMAIL_API_KEY")
    agentmail_api_base: str = Field(default="https://api.agentmail.to", alias="AGENTMAIL_API_BASE")
    agentmail_webhook_secret: str | None = Field(default=None, alias="AGENTMAIL_WEBHOOK_SECRET")
    agentmail_inbox_address: str | None = Field(default=None, alias="AGENTMAIL_INBOX_ADDRESS")

    google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(default=None, alias="GOOGLE_CLIENT_SECRET")
    google_refresh_token: str | None = Field(default=None, alias="GOOGLE_REFRESH_TOKEN")
    google_calendar_id: str = Field(default="primary", alias="GOOGLE_CALENDAR_ID")
    workspace_email_domain: str | None = Field(default=None, alias="WORKSPACE_EMAIL_DOMAIN")
    calendar_alias_map_json: str | None = Field(default=None, alias="CALENDAR_ALIAS_MAP_JSON")

    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    sqlite_path: str = Field(default="data/agent.db", alias="SQLITE_PATH")

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)

    @property
    def sqlite_file(self) -> Path:
        return Path(self.sqlite_path)

    @property
    def telegram_allowed_chat_ids(self) -> set[str]:
        if self.telegram_allowed_chat_ids_raw:
            return {
                chat_id.strip()
                for chat_id in self.telegram_allowed_chat_ids_raw.split(",")
                if chat_id.strip()
            }
        if self.telegram_admin_chat_id:
            return {self.telegram_admin_chat_id.strip()}
        return set()

    @property
    def calendar_alias_map(self) -> dict[str, str]:
        if not self.calendar_alias_map_json:
            return {}
        try:
            value = json.loads(self.calendar_alias_map_json)
        except json.JSONDecodeError:
            return {}
        if not isinstance(value, dict):
            return {}
        return {str(key).strip().lower(): str(mapped_value).strip() for key, mapped_value in value.items()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
