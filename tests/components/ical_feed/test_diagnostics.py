"""Diagnostics tests for the iCal feed integration."""

from __future__ import annotations

from tests.components.ical_feed.common import use_repo_config_dir
from unittest.mock import patch

from homeassistant.core import HomeAssistant

from custom_components.ical_feed import diagnostics as diag_module, util
from custom_components.ical_feed.const import CONF_CALENDARS, CONF_SECRET, DOMAIN
from custom_components.ical_feed.diagnostics import async_get_config_entry_diagnostics
from tests.common import MockConfigEntry


async def test_diagnostics_redacts_secret(hass: HomeAssistant) -> None:
    """Ensure diagnostics redact the shared secret."""
    use_repo_config_dir(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CALENDARS: ["calendar.test"],
            CONF_SECRET: "topsecret",
        },
        title="My feed",
    )
    entry.add_to_hass(hass)

    with patch.object(
        diag_module, "build_feed_url", return_value="https://example.test/ical/topsecret/my_feed.ics"
    ), patch.object(diag_module, "mask_feed_url", util.mask_feed_url):
        diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["data"][CONF_SECRET] == "**REDACTED**"
    expected_url = util.mask_feed_url("https://example.test/ical/topsecret/my_feed.ics")
    assert diagnostics["feed_url"] == expected_url
