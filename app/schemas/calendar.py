from datetime import datetime

from pydantic import BaseModel, Field


class TimeWindow(BaseModel):
    start_at: datetime
    end_at: datetime
    timezone: str


class AvailabilityRequest(BaseModel):
    start_at: datetime
    end_at: datetime
    duration_minutes: int = Field(default=30, ge=15)
    timezone: str


class AvailabilitySlot(BaseModel):
    start_at: datetime
    end_at: datetime
    timezone: str


class CalendarEventInput(BaseModel):
    title: str
    start_at: datetime
    end_at: datetime
    timezone: str
    description: str | None = None
    attendees: list[str] = Field(default_factory=list)
    location: str | None = None


class CalendarEventUpdate(BaseModel):
    event_id: str
    title: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    timezone: str | None = None
    description: str | None = None
    attendees: list[str] | None = None
    location: str | None = None
