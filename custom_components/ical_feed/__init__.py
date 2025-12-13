"""Home Assistant setup for the iCal feed integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.helpers.event import async_track_entity_registry_updated_event
from homeassistant.helpers.issue_registry import IssueSeverity
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_CALENDARS,
    DATA_CACHE,
    DATA_ENTRIES,
    DATA_LISTENERS,
    DATA_VIEW,
    DOMAIN,
)
from .http import ICalFeedView

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the iCal feed namespace."""
    domain_data = _async_get_domain_data(hass)
    if not domain_data[DATA_VIEW]:
        hass.http.register_view(ICalFeedView(hass))
        domain_data[DATA_VIEW] = True
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up an iCal feed entry."""
    domain_data = _async_get_domain_data(hass)
    domain_data[DATA_ENTRIES][entry.entry_id] = entry
    domain_data[DATA_CACHE].pop(entry.entry_id, None)
    _async_register_registry_listener(hass, entry)
    _async_check_missing_calendars(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_update_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    domain_data = _async_get_domain_data(hass)
    domain_data[DATA_ENTRIES].pop(entry.entry_id, None)
    domain_data[DATA_CACHE].pop(entry.entry_id, None)
    _async_remove_registry_listener(hass, entry.entry_id)
    ir.async_delete_issue(hass, DOMAIN, _build_issue_id(entry.entry_id))
    return True


async def _update_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle updates triggered by the options flow."""
    domain_data = _async_get_domain_data(hass)
    domain_data[DATA_ENTRIES][entry.entry_id] = entry
    domain_data[DATA_CACHE].pop(entry.entry_id, None)
    _async_register_registry_listener(hass, entry)
    _async_check_missing_calendars(hass, entry)


def _async_get_domain_data(hass: HomeAssistant) -> dict[str, Any]:
    """Return the integration data container."""
    return hass.data.setdefault(
        DOMAIN,
        {
            DATA_ENTRIES: {},
            DATA_LISTENERS: {},
            DATA_VIEW: False,
            DATA_CACHE: {},
        },
    )


def _async_register_registry_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Track entity registry updates for the configured calendars."""
    domain_data = _async_get_domain_data(hass)
    _async_remove_registry_listener(hass, entry.entry_id)
    calendars = [entity_id.lower() for entity_id in entry.data.get(CONF_CALENDARS, [])]
    if not calendars:
        return

    entry_id = entry.entry_id

    @callback
    def _handle_registry_event(event) -> None:
        if entry_id not in domain_data[DATA_ENTRIES]:
            return
        _async_check_missing_calendars(hass, domain_data[DATA_ENTRIES][entry_id])

    listener = async_track_entity_registry_updated_event(
        hass, calendars, _handle_registry_event
    )
    domain_data[DATA_LISTENERS][entry.entry_id] = listener


def _async_remove_registry_listener(hass: HomeAssistant, entry_id: str) -> None:
    """Remove a previously registered registry listener."""
    domain_data = _async_get_domain_data(hass)
    if unsub := domain_data[DATA_LISTENERS].pop(entry_id, None):
        unsub()


def _build_issue_id(entry_id: str) -> str:
    """Return a unique issue id for an entry."""
    return f"{entry_id}_missing_calendar"


def _async_check_missing_calendars(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create or clear a repair issue when a calendar disappears."""
    registry = er.async_get(hass)
    missing = [
        entity_id
        for entity_id in entry.data.get(CONF_CALENDARS, [])
        if registry.async_get(entity_id) is None
    ]

    issue_id = _build_issue_id(entry.entry_id)
    if missing:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=True,
            issue_domain=DOMAIN,
            severity=IssueSeverity.ERROR,
            translation_key="missing_calendar",
            translation_placeholders={
                "entry": entry.title or entry.entry_id,
                "calendars": ", ".join(missing),
            },
        )
        _LOGGER.debug(
            "Missing calendars for %s detected: %s",
            entry.entry_id,
            ", ".join(missing),
        )
        return

    ir.async_delete_issue(hass, DOMAIN, issue_id)
    _LOGGER.debug("All calendars available again for %s", entry.entry_id)
