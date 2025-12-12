"""Tests for the iCal feed utilities."""

from __future__ import annotations

import logging
from unittest.mock import patch

from homeassistant.core import HomeAssistant

from custom_components.ical_feed import util
from custom_components.ical_feed.const import CONF_SECRET

from tests.common import MockConfigEntry


def _make_entry(title: str = "My Feed", entry_id: str = "entry-id") -> MockConfigEntry:
    """Create a config entry with default data."""
    return MockConfigEntry(
        entry_id=entry_id,
        data={
            CONF_SECRET: "secret-token",
        },
        title=title,
    )


def test_build_feed_url_with_base_url(hass: HomeAssistant) -> None:
    """Feed URL should include the base URL when available."""
    entry = _make_entry()
    with patch.object(util, "_get_base_url", return_value="https://example.test"):
        url = util.build_feed_url(hass, entry)
    assert url == "https://example.test/ical/secret-token/my_feed.ics"


def test_build_feed_url_without_base_url(hass: HomeAssistant) -> None:
    """Feed URL falls back to a relative path."""
    entry = _make_entry()
    with patch("custom_components.ical_feed.util._get_base_url", return_value=""):
        url = util.build_feed_url(hass, entry)
    assert url == "/ical/secret-token/my_feed.ics"


def test_mask_feed_url_redacts_secret() -> None:
    """Secrets are masked even if the link is shared."""
    original = "https://example.test/ical/abcdefgh/office/feed.ics"
    masked = util.mask_feed_url(original)
    assert masked != original
    assert "abcdefgh" not in masked
    assert "…" in masked


def test_get_feed_slug_falls_back_to_entry_id() -> None:
    """Titles without valid slugs fall back to the entry ID."""
    entry = _make_entry("!!!", entry_id="entry-1")
    slug = util.get_feed_slug(entry)
    assert slug == "entry-1"


def test_log_feed_summary(caplog) -> None:
    """The log summary redacts the secret portion."""
    caplog.set_level("INFO")
    entry = _make_entry("Office feed")
    logger = logging.getLogger(__name__)
    util.log_feed_summary(logger, entry, "https://example/ical/token/feed.ics", 3)
    assert "Office feed served 3 events" in caplog.text
    assert "token" not in caplog.text
