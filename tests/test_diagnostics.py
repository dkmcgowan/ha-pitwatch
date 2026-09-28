"""Diagnostics, which end up pasted into public bug reports."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitwatch.diagnostics import async_get_config_entry_diagnostics

from .conftest import TOKEN


async def test_the_token_never_reaches_a_bug_report(
    hass: HomeAssistant, entry: MockConfigEntry, client, stream
) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    found = await async_get_config_entry_diagnostics(hass, entry)

    assert TOKEN not in repr(found)
    assert found["entry"]["api_token"] == "**REDACTED**"
    assert found["state"]["site"]["name"] == "Test Building"
