"""The PitWatch integration.

PitWatch watches the sewage ejector pumps in a building: the current each motor
draws, the panel's contacts, the floats, and the rules that turn all of that
into alerts. This brings its reading of one building into Home Assistant,
pushed as it changes. PitWatch keeps the logic; Home Assistant gets its
conclusions.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_TOKEN, CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PitWatchClient
from .coordinator import PitWatchCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.SENSOR,
]

type PitWatchConfigEntry = ConfigEntry[PitWatchCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: PitWatchConfigEntry) -> bool:
    """Set up one PitWatch building from a config entry."""
    client = PitWatchClient(
        async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_API_TOKEN]
    )
    coordinator = PitWatchCoordinator(hass, entry, client)
    # No try/except: the coordinator turns a refused token into
    # ConfigEntryAuthFailed and anything else into ConfigEntryNotReady, which
    # is what Home Assistant wants to see here.
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # After the platforms, so the event entity is listening before the first
    # alert can arrive.
    coordinator.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PitWatchConfigEntry) -> bool:
    """Unload a config entry. The stream task stops with it."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
