from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import Settings
from app.schemas.calendar import (
    AvailabilityRequest,
    AvailabilityResult,
    AvailabilitySlot,
    BusyWindow,
    CalendarEventInput,
    CalendarEventUpdate,
)
from app.services.reliability import retry_async

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


class CalendarAPIError(RuntimeError):
    def __init__(
        self,
        *,
        operation: str,
        message: str,
        status_code: int | None = None,
        response_text: str | None = None,
    ):
        super().__init__(message)
        self.operation = operation
        self.status_code = status_code
        self.response_text = response_text


class GoogleCalendarService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._service = None

    async def check_availability(self, request: AvailabilityRequest) -> AvailabilityResult:
        calendar_ids = request.calendar_ids or [self.settings.google_calendar_id]
        busy_windows = await self._fetch_busy_windows(
            request.start_at,
            request.end_at,
            request.timezone,
            calendar_ids,
        )
        cursor = request.start_at
        slots: list[AvailabilitySlot] = []
        step = timedelta(minutes=30)
        duration = timedelta(minutes=request.duration_minutes)
        while cursor + duration <= request.end_at:
            candidate_end = cursor + duration
            if not any(self._overlaps(cursor, candidate_end, busy["start"], busy["end"]) for busy in busy_windows):
                slots.append(AvailabilitySlot(start_at=cursor, end_at=candidate_end, timezone=request.timezone))
            cursor += step
        return AvailabilityResult(
            queried_calendar_ids=calendar_ids,
            busy_windows=[
                BusyWindow(
                    calendar_id=busy["calendar_id"],
                    start_at=busy["start"],
                    end_at=busy["end"],
                    timezone=request.timezone,
                )
                for busy in busy_windows
            ],
            slots=slots,
        )

    async def create_event(self, event: CalendarEventInput) -> dict[str, Any]:
        payload = {
            "summary": event.title,
            "description": event.description,
            "location": event.location,
            "start": {"dateTime": event.start_at.isoformat(), "timeZone": event.timezone},
            "end": {"dateTime": event.end_at.isoformat(), "timeZone": event.timezone},
            "attendees": [{"email": email} for email in event.attendees],
        }
        return await retry_async(lambda: asyncio.to_thread(self._events_insert, payload))

    async def update_event(self, event: CalendarEventUpdate) -> dict[str, Any]:
        body = {key: value for key, value in self._event_update_payload(event).items() if value is not None}
        return await retry_async(lambda: asyncio.to_thread(self._events_patch, event.event_id, body))

    async def delete_event(self, event_id: str) -> dict[str, Any]:
        return await retry_async(lambda: asyncio.to_thread(self._events_delete, event_id))

    async def upcoming_context(self, days: int = 14) -> list[dict[str, Any]]:
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        max_time = (datetime.now(UTC) + timedelta(days=days)).isoformat().replace("+00:00", "Z")
        events = await asyncio.to_thread(self._events_list, now, max_time)
        return events.get("items", [])

    async def _fetch_busy_windows(
        self,
        start_at: datetime,
        end_at: datetime,
        timezone: str,
        calendar_ids: list[str],
    ) -> list[dict[str, Any]]:
        if not self._credentials_ready:
            return []
        try:
            response = await asyncio.to_thread(self._freebusy_query, start_at, end_at, timezone, calendar_ids)
        except HttpError as exc:
            response_text = exc.content.decode("utf-8", errors="replace") if getattr(exc, "content", None) else None
            raise CalendarAPIError(
                operation="freebusy_query",
                message="Google Calendar free/busy query failed.",
                status_code=getattr(exc.resp, "status", None),
                response_text=response_text,
            ) from exc
        busy_windows: list[dict[str, Any]] = []
        for calendar_id, calendar_data in response.get("calendars", {}).items():
            busy = calendar_data.get("busy", [])
            for item in busy:
                busy_windows.append(
                    {
                        "calendar_id": calendar_id,
                        "start": datetime.fromisoformat(item["start"].replace("Z", "+00:00")),
                        "end": datetime.fromisoformat(item["end"].replace("Z", "+00:00")),
                    }
                )
        return busy_windows

    @property
    def _credentials_ready(self) -> bool:
        return all(
            [
                self.settings.google_client_id,
                self.settings.google_client_secret,
                self.settings.google_refresh_token,
            ]
        )

    def _build_service(self):
        if self._service is not None:
            return self._service
        if not self._credentials_ready:
            raise RuntimeError("Google Calendar credentials are not configured.")
        credentials = Credentials(
            token=None,
            refresh_token=self.settings.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.settings.google_client_id,
            client_secret=self.settings.google_client_secret,
            scopes=SCOPES,
        )
        self._service = build("calendar", "v3", credentials=credentials, cache_discovery=False)
        return self._service

    def _freebusy_query(
        self,
        start_at: datetime,
        end_at: datetime,
        timezone: str,
        calendar_ids: list[str],
    ) -> dict[str, Any]:
        if not self._credentials_ready:
            return {"calendars": {calendar_id: {"busy": []} for calendar_id in calendar_ids}}
        service = self._build_service()
        return (
            service.freebusy()
            .query(
                body={
                    "timeMin": start_at.isoformat(),
                    "timeMax": end_at.isoformat(),
                    "timeZone": timezone,
                    "items": [{"id": calendar_id} for calendar_id in calendar_ids],
                }
            )
            .execute()
        )

    def _events_insert(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._credentials_ready:
            return {"status": "simulated", "event": payload}
        service = self._build_service()
        return service.events().insert(calendarId=self.settings.google_calendar_id, body=payload).execute()

    def _events_patch(self, event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._credentials_ready:
            return {"status": "simulated", "event_id": event_id, "event": payload}
        service = self._build_service()
        return service.events().patch(
            calendarId=self.settings.google_calendar_id,
            eventId=event_id,
            body=payload,
        ).execute()

    def _events_delete(self, event_id: str) -> dict[str, Any]:
        if not self._credentials_ready:
            return {"status": "simulated", "event_id": event_id}
        service = self._build_service()
        service.events().delete(calendarId=self.settings.google_calendar_id, eventId=event_id).execute()
        return {"status": "deleted", "event_id": event_id}

    def _events_list(self, time_min: str, time_max: str) -> dict[str, Any]:
        if not self._credentials_ready:
            return {"items": []}
        service = self._build_service()
        return (
            service.events()
            .list(
                calendarId=self.settings.google_calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

    @staticmethod
    def _event_update_payload(event: CalendarEventUpdate) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if event.title is not None:
            payload["summary"] = event.title
        if event.description is not None:
            payload["description"] = event.description
        if event.location is not None:
            payload["location"] = event.location
        if event.attendees is not None:
            payload["attendees"] = [{"email": email} for email in event.attendees]
        if event.start_at is not None and event.end_at is not None and event.timezone is not None:
            payload["start"] = {"dateTime": event.start_at.isoformat(), "timeZone": event.timezone}
            payload["end"] = {"dateTime": event.end_at.isoformat(), "timeZone": event.timezone}
        return payload

    @staticmethod
    def _overlaps(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
        return start_a < end_b and start_b < end_a
