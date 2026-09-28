"""Setting up a building, and what the stream does to it."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitwatch.api import PitWatchConnectionError
from custom_components.pitwatch.const import EVENT_ALERT

from .conftest import FakeStream, alert

PREFIX = "test_building"


@pytest.fixture(autouse=True)
def no_waiting():
    """Reconnect at once, rather than after the real five seconds."""
    with patch("custom_components.pitwatch.coordinator.RECONNECT_MIN_S", 0):
        yield


async def _set_up(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _settle(hass: HomeAssistant) -> None:
    """Let the stream task hand on whatever was just sent."""
    for _ in range(5):
        await hass.async_block_till_done()


def _state(hass: HomeAssistant, entity_id: str) -> str:
    found = hass.states.get(entity_id)
    assert found is not None, f"{entity_id} does not exist"
    return found.state


async def test_the_building_arrives_as_a_device_with_its_pumps(
    hass: HomeAssistant, entry: MockConfigEntry, client, stream: FakeStream
) -> None:
    await _set_up(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert _state(hass, f"binary_sensor.{PREFIX}_pump_1_running") == STATE_OFF
    assert _state(hass, f"binary_sensor.{PREFIX}_high_water") == STATE_OFF
    assert _state(hass, f"sensor.{PREFIX}_pump_1_runs_today") == "98"
    assert _state(hass, f"sensor.{PREFIX}_pump_2_panel_display") == "lead"
    assert _state(hass, f"sensor.{PREFIX}_rain_in_the_last_24_hours") == "7.6"
    assert _state(hass, f"binary_sensor.{PREFIX}_needs_attention") == STATE_OFF
    assert _state(hass, f"event.{PREFIX}_alerts") == STATE_UNKNOWN


async def test_a_snapshot_on_the_stream_is_the_new_state(
    hass: HomeAssistant, entry: MockConfigEntry, client, stream: FakeStream, snapshot
) -> None:
    await _set_up(hass, entry)

    running: dict[str, Any] = {**snapshot, "pumps": [dict(p) for p in snapshot["pumps"]]}
    running["pumps"][0].update(running=True, current=15.3, display="ON")
    stream.send({"type": "snapshot", "data": running})
    await _settle(hass)

    assert _state(hass, f"binary_sensor.{PREFIX}_pump_1_running") == STATE_ON
    assert _state(hass, f"sensor.{PREFIX}_pump_1_current") == "15.3"
    assert _state(hass, f"binary_sensor.{PREFIX}_live_connection") == STATE_ON


async def test_an_alert_fires_the_entity_and_the_bus_with_its_sentence(
    hass: HomeAssistant, entry: MockConfigEntry, client, stream: FakeStream, snapshot
) -> None:
    heard: list[Event] = []
    hass.bus.async_listen(EVENT_ALERT, heard.append)
    await _set_up(hass, entry)
    stream.send({"type": "snapshot", "data": snapshot})

    stream.send({"type": "alert", "event": "raised", "alert": alert(7)})
    await _settle(hass)

    fired = hass.states.get(f"event.{PREFIX}_alerts")
    assert fired.attributes["event_type"] == "raised"
    assert fired.attributes["message"] == "High water alert at Test Building."
    assert [e.data["event"] for e in heard] == ["raised"]
    assert heard[0].data["site"] == "Test Building"

    stream.send(
        {
            "type": "alert",
            "event": "cleared",
            "alert": alert(
                7,
                cleared_at="2026-09-28T12:00:20+00:00",
                cleared_message="The high water alert has cleared.",
            ),
        }
    )
    await _settle(hass)

    fired = hass.states.get(f"event.{PREFIX}_alerts")
    assert fired.attributes["event_type"] == "cleared"
    assert fired.attributes["message"] == "The high water alert has cleared."


async def test_an_alert_is_said_once_however_it_arrives(
    hass: HomeAssistant, entry: MockConfigEntry, client, stream: FakeStream, snapshot
) -> None:
    """Announce each alert once, in the order they came.

    After a drop the missed alerts are fetched and announced, and the stream
    may send the same one again.
    """
    heard: list[Event] = []
    hass.bus.async_listen(EVENT_ALERT, heard.append)
    await _set_up(hass, entry)
    stream.send({"type": "snapshot", "data": snapshot})
    await _settle(hass)

    # It drops, and while it is down an alert is raised and cleared.
    client.alerts.return_value = [
        alert(9, cleared_at="2026-09-28T12:01:00+00:00", cleared_message="Cleared.")
    ]
    stream.drop()
    await _settle(hass)
    stream.send({"type": "snapshot", "data": snapshot})
    await _settle(hass)
    # And the stream, reconnected, sends the clear as well.
    stream.send(
        {
            "type": "alert",
            "event": "cleared",
            "alert": alert(9, cleared_at="2026-09-28T12:01:00+00:00", cleared_message="Cleared."),
        }
    )
    await _settle(hass)

    assert [(e.data["event"], e.data["alert_id"]) for e in heard] == [
        ("raised", 9),
        ("cleared", 9),
    ]


async def test_what_happened_before_home_assistant_started_is_not_news(
    hass: HomeAssistant, entry: MockConfigEntry, client, stream: FakeStream, snapshot
) -> None:
    heard: list[Event] = []
    hass.bus.async_listen(EVENT_ALERT, heard.append)
    client.alerts.return_value = [alert(3, cleared_at="2026-09-27T06:31:31+00:00")]

    await _set_up(hass, entry)
    stream.send({"type": "snapshot", "data": snapshot})
    await _settle(hass)

    assert heard == []


async def test_an_open_warning_is_attention_and_info_is_not(
    hass: HomeAssistant, entry: MockConfigEntry, client, stream: FakeStream, snapshot
) -> None:
    await _set_up(hass, entry)

    snapshot["alerts"]["open"] = [alert(1, severity="info", rule="run_drift")]
    stream.send({"type": "snapshot", "data": snapshot})
    await _settle(hass)
    assert _state(hass, f"binary_sensor.{PREFIX}_needs_attention") == STATE_OFF

    snapshot["alerts"]["open"].append(alert(2))
    stream.send({"type": "snapshot", "data": {**snapshot}})
    await _settle(hass)
    attention = hass.states.get(f"binary_sensor.{PREFIX}_needs_attention")
    assert attention.state == STATE_ON
    assert attention.attributes["alerts"][0]["message"] == "High water alert at Test Building."


async def test_the_buttons_are_only_there_when_the_token_may_press(
    hass: HomeAssistant, entry: MockConfigEntry, client, stream: FakeStream
) -> None:
    await _set_up(hass, entry)

    assert hass.states.get(f"button.{PREFIX}_reset_panel_alarm") is None


async def test_a_pressing_token_gets_buttons_that_press(
    hass: HomeAssistant, entry: MockConfigEntry, client, stream: FakeStream, snapshot
) -> None:
    snapshot["panel_button"]["allowed"] = True
    await _set_up(hass, entry)

    await hass.services.async_call(
        "button", "press", {"entity_id": f"button.{PREFIX}_reset_panel_alarm"}, blocking=True
    )

    client.press.assert_awaited_once_with("reset")


async def test_a_revoked_token_asks_for_a_new_one(
    hass: HomeAssistant, entry: MockConfigEntry, client, stream: FakeStream, snapshot
) -> None:
    await _set_up(hass, entry)
    stream.send({"type": "snapshot", "data": snapshot})
    await _settle(hass)

    stream.refuse()
    await _settle(hass)

    flows = hass.config_entries.flow.async_progress_by_handler("pitwatch")
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]
    assert _state(hass, f"binary_sensor.{PREFIX}_live_connection") == STATE_OFF


async def test_pitwatch_down_at_start_is_retried_not_failed(
    hass: HomeAssistant, entry: MockConfigEntry, client
) -> None:
    client.state = AsyncMock(side_effect=PitWatchConnectionError("nope"))
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_it_unloads(hass: HomeAssistant, entry: MockConfigEntry, client, stream) -> None:
    await _set_up(hass, entry)

    assert await hass.config_entries.async_unload(entry.entry_id)

    assert entry.state is ConfigEntryState.NOT_LOADED
