"""Diagnostics support for the iCal feed integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_CALENDARS, CONF_SECRET, DOMAIN
from .util import build_feed_url, mask_feed_url

TO_REDACT = {CONF_SECRET}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    feed_url = build_feed_url(hass, entry)
    return {
        "domain": DOMAIN,
        "entry_id": entry.entry_id,
        "title": entry.title,
        "data": async_redact_data(entry.data, TO_REDACT),
        "feed_url": mask_feed_url(feed_url),
        "calendars": entry.data.get(CONF_CALENDARS, []),
    }
