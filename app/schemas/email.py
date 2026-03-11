from datetime import datetime

from pydantic import BaseModel, Field


class AgentMailEnvelope(BaseModel):
    event_type: str = "message.received"
    event_id: str
    inbox_id: str
    thread_id: str
    message_id: str
    subject: str
    sender: str
    sender_addresses: list[str] = Field(default_factory=list)
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    preview: str = ""
    body_text: str = ""
    body_html: str | None = None
    quoted_text: str | None = None
    received_at: datetime


class EmailReplyRequest(BaseModel):
    inbox_id: str
    message_id: str
    body_text: str
    body_html: str | None = None
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    reply_to: list[str] = Field(default_factory=list)
    reply_all: bool = True
