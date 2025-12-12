"""Tests for repair issues in the iCal feed integration."""

from __future__ import annotations

import importlib

from tests.components.ical_feed.common import use_repo_config_dir
from homeassistant.helpers import entity_registry as er, issue_registry as ir

from custom_components.ical_feed.const import CONF_CALENDARS, DOMAIN
from tests.common import MockConfigEntry


async def test_missing_calendar_issue_created_and_cleared(
    hass, issue_registry: ir.IssueRegistry
) -> None:
    """Test that the missing calendar issue is raised and cleared."""
    use_repo_config_dir(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CALENDARS: ["calendar.office"]},
        title="Office feed",
    )
    entry.add_to_hass(hass)

    ical_init = importlib.import_module("custom_components.ical_feed.__init__")
    ical_init._async_check_missing_calendars(hass, entry)

    issue_id = f"{entry.entry_id}_missing_calendar"
    issue = issue_registry.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert "calendar.office" in issue.translation_placeholders["calendars"]

    registry = er.async_get(hass)
    registry.async_get_or_create(
        "calendar", "test", "office", suggested_object_id="office"
    )

    ical_init._async_check_missing_calendars(hass, entry)

    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None
