"""Tests for the iCal feed config flow."""

from __future__ import annotations

from unittest.mock import patch

from tests.components.ical_feed.common import use_repo_config_dir
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.ical_feed.const import (
    CONF_CALENDARS,
    CONF_FILTER_REGEX,
    CONF_FUTURE_DAYS,
    CONF_PAST_DAYS,
    CONF_REGENERATE_LINK,
    CONF_SECRET,
    CONF_TITLE_REGEX,
    CONF_TITLE_REPLACEMENT,
    DOMAIN,
    DEFAULT_FUTURE_DAYS,
    DEFAULT_PAST_DAYS,
)
from tests.common import MockConfigEntry


async def test_flow_aborts_without_calendars(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Test the user step aborts when no calendar entities exist."""
    use_repo_config_dir(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_calendars"


async def test_flow_creates_entry(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Test selecting a calendar creates a config entry."""
    use_repo_config_dir(hass)
    registry = er.async_get(hass)
    calendar_entry = registry.async_get_or_create(
        "calendar",
        "test",
        "1234",
        suggested_object_id="family",
        original_name="Family calendar",
    )

    with patch(
        "custom_components.ical_feed.config_flow.generate_secret",
        return_value="super-secret",
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_CALENDARS: calendar_entry.entity_id,
                CONF_PAST_DAYS: 3,
                CONF_FUTURE_DAYS: 5,
            },
        )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Family calendar"
    assert result2["data"][CONF_CALENDARS] == [calendar_entry.entity_id]
    assert result2["data"][CONF_PAST_DAYS] == 3
    assert result2["data"][CONF_FUTURE_DAYS] == 5
    assert result2["data"][CONF_SECRET] == "super-secret"


async def test_options_flow_updates_entry(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Test the options flow updates the entry data."""
    use_repo_config_dir(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CALENDARS: ["calendar.test"],
            CONF_PAST_DAYS: DEFAULT_PAST_DAYS,
            CONF_FUTURE_DAYS: DEFAULT_FUTURE_DAYS,
            CONF_SECRET: "initial-secret",
            CONF_TITLE_REGEX: "",
            CONF_TITLE_REPLACEMENT: "",
            CONF_FILTER_REGEX: "",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.ical_feed.config_flow.build_feed_url",
            return_value="https://example.test/ical/secret/feed.ics",
        ),
        patch(
            "custom_components.ical_feed.config_flow.generate_secret",
            return_value="rotated",
        ),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        result2 = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_PAST_DAYS: 10,
                CONF_FUTURE_DAYS: 12,
                CONF_TITLE_REGEX: "^(.*)$",
                CONF_TITLE_REPLACEMENT: r"\1 updated",
                CONF_FILTER_REGEX: "",
                CONF_REGENERATE_LINK: True,
            },
        )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_PAST_DAYS] == 10
    assert entry.data[CONF_FUTURE_DAYS] == 12
    assert entry.data[CONF_TITLE_REGEX] == "^(.*)$"
    assert entry.data[CONF_TITLE_REPLACEMENT] == r"\1 updated"
    assert entry.data[CONF_FILTER_REGEX] == ""
    assert entry.data[CONF_SECRET] == "rotated"


async def test_reauth_flow_rotates_secret(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Test the reauthentication flow regenerates the shared secret."""
    use_repo_config_dir(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CALENDARS: ["calendar.test"],
            CONF_PAST_DAYS: DEFAULT_PAST_DAYS,
            CONF_FUTURE_DAYS: DEFAULT_FUTURE_DAYS,
            CONF_SECRET: "initial-secret",
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ical_feed.config_flow.generate_secret",
        return_value="new-secret",
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data=entry.data,
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={},
        )

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "reauth_successful"
    assert entry.data[CONF_SECRET] == "new-secret"
