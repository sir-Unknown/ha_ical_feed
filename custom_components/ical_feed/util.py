"""Utilities for the iCal feed integration."""

from __future__ import annotations

import base64
from logging import Logger
import secrets

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import network
from homeassistant.util import slugify

from .const import CONF_SECRET, ICAL_EXTENSION, PUBLIC_FEED_PATH


def generate_secret() -> str:
    """Create a 512-bit URL-safe secret used in the shared URL."""
    raw_secret = secrets.token_bytes(64)
    encoded = base64.urlsafe_b64encode(raw_secret).decode("ascii")
    return encoded.rstrip("=")


def build_feed_url(hass: HomeAssistant, entry: ConfigEntry) -> str:
    """Construct a URL that points to the feed."""
    secret = entry.data.get(CONF_SECRET, "")
    feed_slug = get_feed_slug(entry)
    base_url = _get_base_url(hass)
    path = f"{PUBLIC_FEED_PATH}/{secret}/{feed_slug}{ICAL_EXTENSION}"
    if not base_url:
        return path
    return f"{base_url}{path}"


def _get_base_url(hass: HomeAssistant) -> str:
    """Return best effort base URL to display to the user."""
    for prefer_external in (True, False):
        try:
            return network.get_url(
                hass,
                allow_internal=True,
                allow_ip=True,
                prefer_external=prefer_external,
            )
        except HomeAssistantError:
            continue
    return ""


def get_feed_slug(entry: ConfigEntry) -> str:
    """Return a URL-safe slug for the feed title."""
    title = entry.title or "ical_feed"
    slug = slugify(title)
    if not slug or slug == "unknown":
        return entry.entry_id
    return slug


def mask_feed_url(url: str) -> str:
    """Return a masked version of the feed URL with the token obfuscated."""
    if not url:
        return ""
    marker = "/ical/"
    if marker not in url:
        return url
    prefix, remainder = url.split(marker, 1)
    parts = remainder.split("/", 2)
    if len(parts) < 2:
        return url
    secret = parts[0]
    if len(secret) <= 6:
        masked_secret = "***"
    else:
        masked_secret = f"{secret[:4]}…{secret[-4:]}"
    parts[0] = masked_secret
    masked_path = "/".join(parts)
    return f"{prefix}{marker}{masked_path}"


def log_feed_summary(
    logger: Logger, entry: ConfigEntry, url: str, event_count: int
) -> None:
    """Log a short summary about a generated feed."""
    masked = mask_feed_url(url)
    entry_name = entry.title or entry.entry_id
    logger.info(
        "Feed %s served %s events (%s)",
        entry_name,
        event_count,
        masked,
    )
