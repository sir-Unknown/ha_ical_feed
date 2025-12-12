"""Common helpers for the ical_feed custom component tests."""

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

from homeassistant import loader
from homeassistant.core import HomeAssistant

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "config"
CUSTOM_COMPONENTS = CONFIG_DIR / "custom_components"

for path in (CONFIG_DIR, CUSTOM_COMPONENTS):
    if str(path) not in sys.path:
        sys.path.append(str(path))


def use_repo_config_dir(hass: HomeAssistant) -> None:
    """Point hass to the repository config dir so custom components load."""
    hass.config.config_dir = str(CONFIG_DIR)
    hass.data.pop(loader.DATA_CUSTOM_COMPONENTS, None)
    for module in list(sys.modules):
        if module == "custom_components" or module.startswith("custom_components."):
            sys.modules.pop(module, None)
    loader._async_mount_config_dir(hass)
    if not getattr(hass, "http", None):
        hass.http = SimpleNamespace(register_view=lambda view: None)
