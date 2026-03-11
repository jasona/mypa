from datetime import datetime

from pydantic import BaseModel


class TelegramInboundMessage(BaseModel):
    chat_id: str
    text: str
    message_id: str
    sent_at: datetime


class TelegramOutboundMessage(BaseModel):
    chat_id: str
    text: str
