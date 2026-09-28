"""The alerts, as an event entity.

Each alert PitWatch raises or clears fires this entity with the same plain
sentence the texts and emails carry. Automations can trigger on it, and the
same thing is fired on the event bus as ``pitwatch_alert`` for YAML that would
rather listen there.
"""

from __future__ import annotations

from typing import Any, ClassVar

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PitWatchConfigEntry
from .coordinator import PitWatchCoordinator, alert_fields
from .entity import PitWatchEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PitWatchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the alerts entity."""
    async_add_entities([AlertEvent(entry.runtime_data)])


class AlertEvent(PitWatchEntity, EventEntity):
    """Fires once for every alert raised, and once when it clears."""

    _attr_translation_key = "alerts"
    _attr_event_types: ClassVar[list[str]] = ["raised", "cleared"]

    def __init__(self, coordinator: PitWatchCoordinator) -> None:
        """One per building."""
        super().__init__(coordinator, "alerts")

    async def async_added_to_hass(self) -> None:
        """Start listening once there is somewhere to write."""
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_alert_listener(self._on_alert))

    @callback
    def _on_alert(self, event: str, alert: dict[str, Any]) -> None:
        self._trigger_event(event, alert_fields(alert, event))
        self.async_write_ha_state()
