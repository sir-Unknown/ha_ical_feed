"""HTTP endpoint that exposes the calendar feed as iCal."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.utils import format_datetime, parsedate_to_datetime
import hashlib
import json
import logging
import secrets
from time import monotonic

from aiohttp import web

from homeassistant.components import calendar
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CALENDARS,
    CONF_FUTURE_DAYS,
    CONF_PAST_DAYS,
    CONF_SECRET,
    DATA_CACHE,
    DATA_ENTRIES,
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

_CACHE_TTL = 30.0


@dataclass(slots=True)
class _FeedCacheEntry:
    payload: str
    etag: str
    last_modified: datetime
    expires_at: float
    config_hash: str


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

        entries = domain_data.get(DATA_ENTRIES)
        if not entries:
            raise web.HTTPNotFound

        entry = None
        for candidate in entries.values():
            candidate_secret = candidate.data.get(CONF_SECRET)
            if isinstance(candidate_secret, str) and secrets.compare_digest(
                candidate_secret, secret
            ):
                entry = candidate
                break
        if entry is None:
            raise web.HTTPNotFound

        if feed != get_feed_slug(entry):
            raise web.HTTPNotFound

        calendars = entry.data.get(CONF_CALENDARS, [])
        past_days = entry.data.get(CONF_PAST_DAYS, DEFAULT_PAST_DAYS)
        future_days = entry.data.get(CONF_FUTURE_DAYS, DEFAULT_FUTURE_DAYS)

        config_hash = _hash_config(
            entry.title,
            calendars,
            past_days,
            future_days,
        )
        cached = _get_cached_feed(
            self.hass, entry.entry_id, config_hash, allow_expired=True
        )
        if cached is not None and cached.expires_at > monotonic():
            response_headers = _build_response_headers(
                cached.etag, cached.last_modified
            )
            if _is_not_modified(request, cached.etag, cached.last_modified):
                return web.Response(
                    status=web.HTTPNotModified.status_code, headers=response_headers
                )
            return web.Response(
                text=cached.payload,
                content_type=ICAL_CONTENT_TYPE,
                headers=response_headers,
            )

        ical_payload, event_count = await _async_generate_calendar(
            self.hass,
            entry.title or "Home Assistant Feed",
            calendars,
            past_days,
            future_days,
        )

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "iCal payload for '%s':\n%s",
                entry.title or entry.entry_id,
                ical_payload,
            )
        log_feed_summary(_LOGGER, entry, str(request.url), event_count)

        etag = _etag_for_payload(ical_payload)
        now = dt_util.utcnow().replace(microsecond=0)
        last_modified = (
            cached.last_modified if cached is not None and cached.etag == etag else now
        )
        _set_cached_feed(
            self.hass,
            entry.entry_id,
            _FeedCacheEntry(
                payload=ical_payload,
                etag=etag,
                last_modified=last_modified,
                expires_at=monotonic() + _CACHE_TTL,
                config_hash=config_hash,
            ),
        )

        response_headers = _build_response_headers(etag, last_modified)
        if _is_not_modified(request, etag, last_modified):
            return web.Response(
                status=web.HTTPNotModified.status_code, headers=response_headers
            )
        return web.Response(
            text=ical_payload,
            content_type=ICAL_CONTENT_TYPE,
            headers=response_headers,
        )


async def _async_generate_calendar(
    hass: HomeAssistant,
    title: str,
    calendars: Iterable[str],
    past_days: int,
    future_days: int,
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
    entities = list(_iter_calendar_entities(component, calendars)) if calendars else []
    if entities:
        results = await asyncio.gather(
            *(
                entity.async_get_events(hass, start_local, end_local)
                for _, entity in entities
            ),
            return_exceptions=True,
        )
        for (entity_id, _), result in zip(entities, results, strict=True):
            if isinstance(result, BaseException):
                if isinstance(result, asyncio.CancelledError):
                    raise result
                if isinstance(result, HomeAssistantError):
                    continue
                _LOGGER.debug(
                    "Unexpected error getting events for %s: %s",
                    entity_id,
                    result,
                )
                continue

            for event in result:
                summary = getattr(event, "summary", "") or ""
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
        lines.extend(_format_event(entity_id, event, utc_now, summary_override=summary))

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
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            return parsed

    if date_only := value.get("date"):
        parsed = dt_util.parse_datetime(date_only)
        if parsed:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            return parsed
        try:
            return datetime.fromisoformat(f"{date_only}T00:00:00").replace(
                tzinfo=dt_util.DEFAULT_TIME_ZONE
            )
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


def _hash_config(
    title: str | None,
    calendars: Iterable[str],
    past_days: int,
    future_days: int,
) -> str:
    """Return a stable hash that identifies the feed configuration."""
    payload = json.dumps(
        {
            "title": title or "",
            "calendars": sorted(calendars),
            "past_days": past_days,
            "future_days": future_days,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _etag_for_payload(payload: str) -> str:
    """Return an RFC-compatible ETag for a generated feed."""
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f'"{digest}"'


def _build_response_headers(etag: str, last_modified: datetime) -> dict[str, str]:
    """Build response headers for cache validation."""
    return {
        "ETag": etag,
        "Last-Modified": format_datetime(dt_util.as_utc(last_modified), usegmt=True),
        "Cache-Control": "private, max-age=0, must-revalidate",
    }


def _etag_matches(header_value: str, etag: str) -> bool:
    """Return True if the request ETag header matches the provided ETag."""
    if not header_value:
        return False
    if header_value.strip() == "*":
        return True
    candidates = [value.strip() for value in header_value.split(",")]
    return etag in candidates


def _is_not_modified(request: web.Request, etag: str, last_modified: datetime) -> bool:
    """Return True if the request indicates the client has a fresh copy."""
    if if_none_match := request.headers.get("If-None-Match"):
        if _etag_matches(if_none_match, etag):
            return True

    if if_modified_since := request.headers.get("If-Modified-Since"):
        try:
            since = parsedate_to_datetime(if_modified_since)
        except (TypeError, ValueError):
            return False
        if since.tzinfo is None:
            since = since.replace(tzinfo=dt_util.UTC)
        return dt_util.as_utc(last_modified) <= dt_util.as_utc(since)

    return False


def _get_cached_feed(
    hass: HomeAssistant, entry_id: str, config_hash: str, *, allow_expired: bool = False
) -> _FeedCacheEntry | None:
    """Return cached feed contents if still valid."""
    domain_data = hass.data.get(DOMAIN)
    if not domain_data:
        return None
    cache: dict[str, _FeedCacheEntry] = domain_data.get(DATA_CACHE, {})
    cached = cache.get(entry_id)
    if cached is None:
        return None
    if cached.config_hash != config_hash:
        return None
    if not allow_expired and cached.expires_at <= monotonic():
        return None
    return cached


def _set_cached_feed(
    hass: HomeAssistant, entry_id: str, cached: _FeedCacheEntry
) -> None:
    """Persist cached feed contents."""
    domain_data = hass.data.get(DOMAIN)
    if not domain_data:
        return
    cache = domain_data.setdefault(DATA_CACHE, {})
    cache[entry_id] = cached
