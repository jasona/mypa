from typing import Any

from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class ToolCallResult(BaseModel):
    name: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ToolExecutionContext(BaseModel):
    source: str
    thread_id: str | None = None
    message_id: str | None = None
