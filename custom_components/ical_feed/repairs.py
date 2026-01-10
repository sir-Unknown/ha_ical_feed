"""Repairs platform for the iCal feed integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import data_entry_flow
from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import CONF_CALENDARS

_MISSING_CALENDAR_SUFFIX = "_missing_calendar"


class MissingCalendarFixFlow(RepairsFlow):
    """Handler for fixing missing calendar entities."""

    def __init__(self, entry_id: str) -> None:
        """Initialize the fix flow."""
        self._entry_id = entry_id

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the first step of a fix flow."""
        if (entry := self.hass.config_entries.async_get_entry(self._entry_id)) is None:
            return self.async_abort(reason="unknown_entry")

        calendar_choices = _get_calendar_choices(self.hass)
        if not calendar_choices:
            return self.async_abort(reason="no_calendars")

        available_defaults = [
            entity_id
            for entity_id in entry.data.get(CONF_CALENDARS, [])
            if entity_id in calendar_choices
        ]
        default_calendars = available_defaults or [next(iter(calendar_choices))]

        selector = _build_calendar_selector(calendar_choices)
        data_schema = vol.Schema(
            {vol.Required(CONF_CALENDARS, default=default_calendars): selector}
        )

        errors: dict[str, str] = {}
        if user_input is not None:
            calendars = user_input.get(CONF_CALENDARS)
            if not calendars:
                errors["base"] = "no_selection"
            else:
                if isinstance(calendars, str):
                    calendars = [calendars]

                updated_data = dict(entry.data)
                updated_data[CONF_CALENDARS] = calendars
                self.hass.config_entries.async_update_entry(entry, data=updated_data)
                return self.async_create_entry(data={})

        description_placeholders = None
        issue_registry = ir.async_get(self.hass)
        if issue := issue_registry.async_get_issue(self.handler, self.issue_id):
            description_placeholders = issue.translation_placeholders

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            description_placeholders=description_placeholders,
            errors=errors,
        )


def _get_calendar_choices(hass: HomeAssistant) -> dict[str, str]:
    """Return a mapping of calendar entity_ids and their names."""
    registry = er.async_get(hass)
    choices: dict[str, str] = {}
    for entity_entry in registry.entities.values():
        if entity_entry.domain != "calendar" or entity_entry.disabled:
            continue
        name = (
            entity_entry.original_name or entity_entry.name or entity_entry.entity_id
        )
        choices[entity_entry.entity_id] = name
    return choices


def _build_calendar_selector(calendar_choices: dict[str, str]) -> SelectSelector:
    """Generate a dropdown selector for calendar choices."""
    options = [
        SelectOptionDict(value=entity_id, label=name)
        for entity_id, name in calendar_choices.items()
    ]
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            multiple=True,
            mode=SelectSelectorMode.DROPDOWN,
            sort=True,
        )
    )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create flow."""
    if issue_id.endswith(_MISSING_CALENDAR_SUFFIX):
        entry_id = (
            data.get("entry_id")
            if data is not None and isinstance(data.get("entry_id"), str)
            else issue_id.removesuffix(_MISSING_CALENDAR_SUFFIX)
        )
        return MissingCalendarFixFlow(entry_id)

    return ConfirmRepairFlow()
