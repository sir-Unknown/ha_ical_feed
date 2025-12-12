"""Tests for the iCal feed HTTP helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re

from tests.components.ical_feed.common import use_repo_config_dir
from homeassistant.components import calendar
from homeassistant.components.calendar.const import DATA_COMPONENT
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.ical_feed import http


class DummyCalendar(calendar.CalendarEntity):
    """Minimal calendar entity used for tests."""

    def __init__(self, entity_id: str, events: list[calendar.CalendarEvent]) -> None:
        self.entity_id = entity_id
        self._events = events

    async def async_get_events(self, hass, start, end):
        return self._events


class DummyComponent:
    """Minimal calendar entity component."""

    def __init__(self, entity: DummyCalendar) -> None:
        self._entity = entity

    def get_entity(self, entity_id: str):
        if entity_id == self._entity.entity_id:
            return self._entity
        return None


async def test_async_generate_calendar_filters(hass: HomeAssistant) -> None:
    """Test the calendar feed applies replacements and filters."""
    use_repo_config_dir(hass)
    now = dt_util.utcnow()
    event_ok = calendar.CalendarEvent(
        start=now + timedelta(hours=2),
        end=now + timedelta(hours=3),
        summary="Original title",
        description="Details",
        location="HQ",
    )
    event_skip = calendar.CalendarEvent(
        start=now + timedelta(hours=4),
        end=now + timedelta(hours=5),
        summary="Ignore me",
    )
    entity = DummyCalendar("calendar.office", [event_skip, event_ok])
    hass.data[DATA_COMPONENT] = DummyComponent(entity)

    ical_payload, count = await http._async_generate_calendar(
        hass,
        "Team Feed",
        ["calendar.office"],
        past_days=1,
        future_days=1,
        title_regex=re.compile("Original"),
        title_replacement="Rewritten",
        filter_regex=re.compile("Ignore"),
    )

    assert count == 1
    assert "X-WR-CALNAME:Team Feed" in ical_payload
    assert "SUMMARY:Rewritten title" in ical_payload
    assert "Ignore me" not in ical_payload


def test_format_event_all_day() -> None:
    """Test all-day events are rendered with date values."""
    event = calendar.CalendarEvent(
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
        summary="Holiday",
    )
    now = datetime(2024, 1, 1, 12, tzinfo=timezone.utc)

    lines = http._format_event(
        "calendar.holiday",
        event,
        now,
        summary_override="Override",
    )

    assert "DTSTART;VALUE=DATE:20240102" in lines
    assert "DTEND;VALUE=DATE:20240103" in lines
    assert "SUMMARY:Override" in lines
    assert any(line.startswith("UID:") for line in lines)


def test_ensure_datetime_handles_dict_inputs() -> None:
    """Test dict representations are parsed to datetimes."""
    dt = http._ensure_datetime({"dateTime": "2024-05-06T07:08:09+00:00"})
    assert isinstance(dt, datetime)
    assert dt.tzinfo == timezone.utc

    midnight = http._ensure_datetime({"date": "2024-05-06"})
    assert midnight == datetime(2024, 5, 6)
