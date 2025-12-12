"""HTTP endpoint that exposes the calendar feed as iCal."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import date, datetime, timedelta
import hashlib
import logging
import re

from aiohttp import web

from homeassistant.components import calendar
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CALENDARS,
    CONF_FILTER_REGEX,
    CONF_FUTURE_DAYS,
    CONF_PAST_DAYS,
    CONF_SECRET,
    CONF_TITLE_REGEX,
    CONF_TITLE_REPLACEMENT,
    DEFAULT_FUTURE_DAYS,
    DEFAULT_PAST_DAYS,
    DOMAIN,
    FEED_PATH,
    ICAL_EXTENSION,
)
from .util import get_feed_slug, log_feed_summary

_LOGGER = logging.getLogger(__name__)
ICAL_CONTENT_TYPE = "text/calendar"

type CalendarEventTuple = tuple[str, calendar.CalendarEvent, str]


class ICalFeedView(HomeAssistantView):
    """Expose calendar subscriptions through the Home Assistant HTTP API."""

    name = "api:ical_feed"
    requires_auth = False
    url = f"{FEED_PATH}" + r"/{secret}/{feed}" + ICAL_EXTENSION

    def __init__(self, hass: HomeAssistant) -> None:
        """Store hass reference."""
        self.hass = hass

    async def get(self, request: web.Request, secret: str, feed: str) -> web.Response:
        """Return the iCal feed for a given entry."""
        domain_data = self.hass.data.get(DOMAIN)
        if not domain_data:
            raise web.HTTPNotFound

        entries = domain_data.get("entries")
        if not entries:
            raise web.HTTPNotFound

        entry = next(
            (entry for entry in entries.values() if entry.data.get(CONF_SECRET) == secret),
            None,
        )
        if entry is None:
            raise web.HTTPNotFound

        if feed != get_feed_slug(entry):
            raise web.HTTPNotFound

        calendars = entry.data.get(CONF_CALENDARS, [])
        past_days = entry.data.get(CONF_PAST_DAYS, DEFAULT_PAST_DAYS)
        future_days = entry.data.get(CONF_FUTURE_DAYS, DEFAULT_FUTURE_DAYS)
        title_regex_str = entry.data.get(CONF_TITLE_REGEX, "")
        title_replacement = entry.data.get(CONF_TITLE_REPLACEMENT, "")
        filter_regex_str = entry.data.get(CONF_FILTER_REGEX, "")

        title_regex = re.compile(title_regex_str) if title_regex_str else None
        filter_regex = re.compile(filter_regex_str) if filter_regex_str else None

        ical_payload, event_count = await _async_generate_calendar(
            self.hass,
            entry.title or "Home Assistant Feed",
            calendars,
            past_days,
            future_days,
            title_regex,
            title_replacement,
            filter_regex,
        )

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "iCal payload for '%s':\n%s",
                entry.title or entry.entry_id,
                ical_payload,
            )
        log_feed_summary(_LOGGER, entry, str(request.url), event_count)

        return web.Response(text=ical_payload, content_type=ICAL_CONTENT_TYPE)


async def _async_generate_calendar(
    hass: HomeAssistant,
    title: str,
    calendars: Iterable[str],
    past_days: int,
    future_days: int,
    title_regex: re.Pattern[str] | None,
    title_replacement: str,
    filter_regex: re.Pattern[str] | None,
) -> tuple[str, int]:
    """Collect events from the selected calendars and produce an iCal payload."""
    utc_now = dt_util.utcnow()
    start = utc_now - timedelta(days=past_days)
    end = utc_now + timedelta(days=future_days)
    start_local = dt_util.as_local(start)
    end_local = dt_util.as_local(end)

    component: EntityComponent[calendar.CalendarEntity] | None = hass.data.get(
        calendar.DATA_COMPONENT
    )
    events: list[CalendarEventTuple] = []
    if calendars:
        for entity_id, entity in _iter_calendar_entities(component, calendars):
            try:
                calendar_events = await entity.async_get_events(
                    hass, start_local, end_local
                )
            except HomeAssistantError:
                continue

            for event in calendar_events:
                summary = getattr(event, "summary", "") or ""
                if title_regex is not None:
                    summary = title_regex.sub(title_replacement, summary)
                if filter_regex is not None and summary and filter_regex.search(summary):
                    continue
                events.append((entity_id, event, summary))

    default_sort_value = utc_now
    events.sort(
        key=lambda item: _ensure_datetime(getattr(item[1], "start", None))
        or default_sort_value
    )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Home Assistant iCal Feed//EN",
        f"X-WR-CALNAME:{_escape_value(title)}",
    ]

    for entity_id, event, summary in events:
        lines.extend(
            _format_event(entity_id, event, utc_now, summary_override=summary)
        )

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n", len(events)


def _format_event(
    entity_id: str,
    event: calendar.CalendarEvent,
    now: datetime,
    summary_override: str | None = None,
) -> list[str]:
    """Translate a Home Assistant calendar event into RFC5545 iCal lines."""
    lines = ["BEGIN:VEVENT"]

    summary_attr = getattr(event, "summary", "") or ""
    uid = getattr(event, "uid", None)
    if not uid:
        uid_source = f"{entity_id}-{event.start}-{summary_attr}"
        uid = hashlib.sha256(uid_source.encode("utf-8")).hexdigest()

    is_all_day = getattr(event, "all_day", False)
    start_dt_value = _ensure_datetime(getattr(event, "start", None)) or now
    end_dt_value = _ensure_datetime(getattr(event, "end", None)) or start_dt_value

    if is_all_day:
        start_dt = dt_util.start_of_local_day(dt_util.as_local(start_dt_value))
        end_dt = dt_util.start_of_local_day(dt_util.as_local(end_dt_value))
        lines.append(f"DTSTART;VALUE=DATE:{start_dt.date().strftime('%Y%m%d')}")
        lines.append(f"DTEND;VALUE=DATE:{end_dt.date().strftime('%Y%m%d')}")
    else:
        lines.append(f"DTSTART:{_format_datetime(start_dt_value)}")
        lines.append(f"DTEND:{_format_datetime(end_dt_value)}")

    lines.append(f"DTSTAMP:{_format_datetime(now)}")
    summary = (
        summary_override
        if summary_override is not None
        else getattr(event, "summary", "") or ""
    )
    description = getattr(event, "description", "")
    location = getattr(event, "location", "")

    lines.append(f"SUMMARY:{_escape_value(summary)}")
    if description:
        lines.append(f"DESCRIPTION:{_escape_value(description)}")
    if location:
        lines.append(f"LOCATION:{_escape_value(location)}")

    lines.append(f"UID:{uid}")
    lines.append("END:VEVENT")
    return lines


def _format_datetime(value: datetime) -> str:
    """Format a datetime to RFC5545 UTC basic format."""
    return dt_util.as_utc(value).strftime("%Y%m%dT%H%M%SZ")


def _escape_value(text: str) -> str:
    """Escape text according to the RFC5545 rules."""
    return (
        text.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def _ensure_datetime(value: datetime | date | dict | None) -> datetime | None:
    """Convert the CalendarEvent representation to a datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(
            value, datetime.min.time(), tzinfo=dt_util.DEFAULT_TIME_ZONE
        )
    if not isinstance(value, dict):
        return None

    if date_time := value.get("dateTime"):
        parsed = dt_util.parse_datetime(date_time)
        if parsed:
            return parsed

    if date_only := value.get("date"):
        parsed = dt_util.parse_datetime(date_only)
        if parsed:
            return parsed
        try:
            return datetime.fromisoformat(f"{date_only}T00:00:00")
        except ValueError:
            return None

    return None


def _iter_calendar_entities(
    component: EntityComponent[calendar.CalendarEntity] | None,
    calendars: Iterable[str],
) -> Iterator[tuple[str, calendar.CalendarEntity]]:
    """Yield the requested calendar entities from the registered component."""
    if component is None:
        return

    for entity_id in calendars:
        if not (entity := component.get_entity(entity_id)):
            continue
        if not isinstance(entity, calendar.CalendarEntity):
            continue
        yield entity_id, entity
