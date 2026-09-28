"""Diagnostics for a PitWatch config entry, with the token taken out."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_TOKEN
from homeassistant.core import HomeAssistant

from . import PitWatchConfigEntry

REDACT = {CONF_API_TOKEN}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PitWatchConfigEntry
) -> dict[str, Any]:
    """Return what the integration knows, for a bug report."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), REDACT),
        "connected": coordinator.connected,
        "state": coordinator.data,
    }
