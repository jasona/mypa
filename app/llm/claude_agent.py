from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from anthropic import AsyncAnthropic

from app.config import Settings
from app.schemas.tools import ToolDefinition

logger = logging.getLogger(__name__)

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class ClaudeAgent:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None

    async def run(
        self,
        prompt: str,
        system_prompt: str,
        tool_handlers: dict[str, ToolHandler],
        extra_context: dict[str, Any] | None = None,
        max_rounds: int = 6,
    ) -> dict[str, Any]:
        if not self.client:
            return {
                "text": "Anthropic API key is not configured. Request received but autonomous reasoning is disabled.",
                "tool_calls": [],
            }

        tools = [tool.model_dump() for tool in self.tool_definitions()]
        user_prompt = prompt
        if extra_context:
            user_prompt = f"{prompt}\n\nContext:\n{json.dumps(extra_context, indent=2, default=str)}"

        messages: list[dict[str, Any]] = [{"role": "user", "content": user_prompt}]
        executed_calls: list[dict[str, Any]] = []
        final_text = ""

        for _ in range(max_rounds):
            response = await self.client.messages.create(
                model=self.settings.anthropic_model,
                max_tokens=1200,
                system=system_prompt,
                messages=messages,
                tools=tools,
            )
            assistant_content: list[dict[str, Any]] = []
            tool_results: list[dict[str, Any]] = []
            text_blocks: list[str] = []

            for block in response.content:
                if block.type == "text":
                    text_blocks.append(block.text)
                    assistant_content.append({"type": "text", "text": block.text})
                    continue
                if block.type != "tool_use":
                    continue
                assistant_content.append(
                    {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
                )
                handler = tool_handlers.get(block.name)
                if not handler:
                    result = {"error": f"Unknown tool: {block.name}"}
                else:
                    result = await handler(block.input)
                executed_calls.append({"name": block.name, "input": block.input, "result": result})
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    }
                )

            messages.append({"role": "assistant", "content": assistant_content})
            if text_blocks:
                final_text = "\n".join(text_blocks).strip()
            if not tool_results:
                break
            messages.append({"role": "user", "content": tool_results})

        logger.info("Claude agent executed %s tool calls.", len(executed_calls))
        return {"text": final_text, "tool_calls": executed_calls}

    @staticmethod
    def tool_definitions() -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="message_telegram",
                description="Send a Telegram message to the operator.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "chat_id": {"type": ["string", "null"]},
                    },
                    "required": ["text"],
                    "additionalProperties": False,
                },
            ),
            ToolDefinition(
                name="check_availability",
                description="Check calendar availability within a time range.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "start_at": {"type": "string", "format": "date-time"},
                        "end_at": {"type": "string", "format": "date-time"},
                        "duration_minutes": {"type": "integer"},
                        "timezone": {"type": "string"},
                    },
                    "required": ["start_at", "end_at", "timezone"],
                    "additionalProperties": False,
                },
            ),
            ToolDefinition(
                name="reserve_slots",
                description="Soft-hold one or more proposed meeting slots for an email thread.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "thread_id": {"type": "string"},
                        "timezone": {"type": "string"},
                        "slots": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "start_at": {"type": "string", "format": "date-time"},
                                    "end_at": {"type": "string", "format": "date-time"},
                                },
                                "required": ["start_at", "end_at"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["thread_id", "timezone", "slots"],
                    "additionalProperties": False,
                },
            ),
            ToolDefinition(
                name="reply_email",
                description="Reply to an email thread with a message.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "inbox_id": {"type": "string"},
                        "message_id": {"type": "string"},
                        "body_text": {"type": "string"},
                        "body_html": {"type": ["string", "null"]},
                        "to": {"type": "array", "items": {"type": "string"}},
                        "cc": {"type": "array", "items": {"type": "string"}},
                        "bcc": {"type": "array", "items": {"type": "string"}},
                        "reply_to": {"type": "array", "items": {"type": "string"}},
                        "reply_all": {"type": "boolean"},
                    },
                    "required": ["inbox_id", "message_id", "body_text"],
                    "additionalProperties": False,
                },
            ),
            ToolDefinition(
                name="create_event",
                description="Create a calendar event.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "start_at": {"type": "string", "format": "date-time"},
                        "end_at": {"type": "string", "format": "date-time"},
                        "timezone": {"type": "string"},
                        "description": {"type": ["string", "null"]},
                        "attendees": {"type": "array", "items": {"type": "string"}},
                        "location": {"type": ["string", "null"]},
                    },
                    "required": ["title", "start_at", "end_at", "timezone"],
                    "additionalProperties": False,
                },
            ),
            ToolDefinition(
                name="update_event",
                description="Update a calendar event.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string"},
                        "title": {"type": ["string", "null"]},
                        "start_at": {"type": ["string", "null"], "format": "date-time"},
                        "end_at": {"type": ["string", "null"], "format": "date-time"},
                        "timezone": {"type": ["string", "null"]},
                        "description": {"type": ["string", "null"]},
                        "attendees": {"type": ["array", "null"], "items": {"type": "string"}},
                        "location": {"type": ["string", "null"]},
                    },
                    "required": ["event_id"],
                    "additionalProperties": False,
                },
            ),
            ToolDefinition(
                name="delete_event",
                description="Delete a calendar event.",
                input_schema={
                    "type": "object",
                    "properties": {"event_id": {"type": "string"}},
                    "required": ["event_id"],
                    "additionalProperties": False,
                },
            ),
        ]
