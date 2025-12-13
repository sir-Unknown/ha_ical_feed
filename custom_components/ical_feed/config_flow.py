"""Config flow for the iCal feed integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_CALENDARS,
    CONF_FUTURE_DAYS,
    CONF_PAST_DAYS,
    CONF_REGENERATE_LINK,
    CONF_SECRET,
    DEFAULT_FUTURE_DAYS,
    DEFAULT_PAST_DAYS,
    DOMAIN,
)
from .util import build_feed_url, generate_secret

_DATA_KEYS = (CONF_CALENDARS, CONF_PAST_DAYS, CONF_FUTURE_DAYS, CONF_SECRET)


class ICalFeedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the iCal feed."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step created from the HA UI."""
        calendar_choices = await self._async_get_calendar_choices()
        if not calendar_choices:
            return self.async_abort(reason="no_calendars")

        errors: dict[str, str] = {}
        if user_input is not None:
            calendar_id = user_input[CONF_CALENDARS]
            if not calendar_id:
                errors["base"] = "no_selection"
            else:
                calendar_name = calendar_choices[calendar_id]
                past_days = user_input.get(CONF_PAST_DAYS, DEFAULT_PAST_DAYS)
                future_days = user_input.get(CONF_FUTURE_DAYS, DEFAULT_FUTURE_DAYS)
                data = {
                    CONF_CALENDARS: [calendar_id],
                    CONF_PAST_DAYS: past_days,
                    CONF_FUTURE_DAYS: future_days,
                    CONF_SECRET: generate_secret(),
                }
                return self.async_create_entry(title=calendar_name, data=data)

        calendar_selector = _build_calendar_selector(calendar_choices)
        default_calendar = next(iter(calendar_choices), "")
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_CALENDARS, default=default_calendar
                ): calendar_selector,
                vol.Required(CONF_PAST_DAYS, default=DEFAULT_PAST_DAYS): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=365)
                ),
                vol.Required(CONF_FUTURE_DAYS, default=DEFAULT_FUTURE_DAYS): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=365)
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start the reauthentication flow."""
        entry_id = self.context.get("entry_id")
        if entry_id is None:
            return self.async_abort(reason="unknown_entry")
        if not (entry := self.hass.config_entries.async_get_entry(entry_id)):
            return self.async_abort(reason="unknown_entry")

        self._reauth_entry = entry
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauth to rotate the shared secret."""
        assert self._reauth_entry is not None
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=vol.Schema({}),
                description_placeholders={
                    "entry": self._reauth_entry.title or self._reauth_entry.entry_id
                },
            )

        new_data = _filter_entry_data(self._reauth_entry.data)
        new_data[CONF_SECRET] = generate_secret()
        self.hass.config_entries.async_update_entry(self._reauth_entry, data=new_data)
        return self.async_abort(reason="reauth_successful")

    async def _async_get_calendar_choices(self) -> dict[str, str]:
        """Return a mapping of calendar entity_ids and their names."""
        registry = er.async_get(self.hass)
        entries = (
            entry for entry in registry.entities.values() if entry.domain == "calendar"
        )
        choices: dict[str, str] = {}
        for entry in entries:
            if entry.disabled:
                continue
            name = entry.original_name or entry.name or entry.entity_id
            choices[entry.entity_id] = name
        return choices

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Return the options flow handler."""
        return ICalFeedOptionsFlow(config_entry)


class ICalFeedOptionsFlow(OptionsFlow):
    """Options flow exposing the feed URL in a textbox."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the options flow handler."""
        self._config_entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the read-only feed URL."""
        feed_url = build_feed_url(self.hass, self._config_entry)
        selected_calendars = self._config_entry.data.get(CONF_CALENDARS, [])
        current_past = self._config_entry.data.get(CONF_PAST_DAYS, DEFAULT_PAST_DAYS)
        current_future = self._config_entry.data.get(
            CONF_FUTURE_DAYS, DEFAULT_FUTURE_DAYS
        )

        if user_input is not None:
            data = _filter_entry_data(self._config_entry.data)
            if user_input.get(CONF_REGENERATE_LINK):
                data[CONF_SECRET] = generate_secret()

            past_days = int(user_input.get(CONF_PAST_DAYS, current_past))
            future_days = int(user_input.get(CONF_FUTURE_DAYS, current_future))

            data[CONF_PAST_DAYS] = past_days
            data[CONF_FUTURE_DAYS] = future_days

            self.hass.config_entries.async_update_entry(self._config_entry, data=data)
            if updated := self.hass.config_entries.async_get_entry(
                self._config_entry.entry_id
            ):
                self._config_entry = updated
            feed_url = build_feed_url(self.hass, self._config_entry)
            return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Optional("feed_url", default=feed_url): _FEED_URL_SELECTOR,
                vol.Required(CONF_PAST_DAYS, default=current_past): _DAYS_SELECTOR,
                vol.Required(CONF_FUTURE_DAYS, default=current_future): _DAYS_SELECTOR,
                vol.Optional(CONF_REGENERATE_LINK, default=False): _BOOLEAN_SELECTOR,
            }
        )

        calendars_description = _format_calendar_names(self.hass, selected_calendars)
        description_placeholders = {
            "feed_url": feed_url,
            "calendars": calendars_description,
        }

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders=description_placeholders,
        )


def _build_calendar_selector(calendar_choices: dict[str, str]) -> SelectSelector:
    """Generate a dropdown selector for calendar choices."""
    options = [
        SelectOptionDict(value=entity_id, label=name)
        for entity_id, name in calendar_choices.items()
    ]
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            multiple=False,
            mode=SelectSelectorMode.DROPDOWN,
            sort=True,
        )
    )


def _filter_entry_data(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return only the supported config entry data keys."""
    return {key: data[key] for key in _DATA_KEYS if key in data}


def _format_calendar_names(hass: HomeAssistant, calendar_ids: list[str]) -> str:
    """Return a comma separated list of configured calendar names."""
    registry = er.async_get(hass)
    names: list[str] = []
    for entity_id in calendar_ids:
        if entity := registry.async_get(entity_id):
            name = entity.original_name or entity.name or entity.entity_id
        else:
            name = entity_id
        names.append(name)
    return ", ".join(names)


_DAYS_SELECTOR = NumberSelector(
    NumberSelectorConfig(
        min=0,
        max=365,
        step=1,
        mode=NumberSelectorMode.BOX,
    )
)
_FEED_URL_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.URL, read_only=True)
)
_BOOLEAN_SELECTOR = BooleanSelector()
