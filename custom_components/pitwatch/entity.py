"""Shared entity plumbing for the PitWatch integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import PitWatchCoordinator


class PitWatchEntity(CoordinatorEntity[PitWatchCoordinator]):
    """Something about one PitWatch building.

    Everything hangs off one device, the building, named the way PitWatch's
    own building switcher names it.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: PitWatchCoordinator, key: str) -> None:
        """Name this entity's slot on the building."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        site = (coordinator.data or {}).get("site", {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(entry.unique_id))},
            manufacturer=MANUFACTURER,
            name=site.get("name") or entry.title,
            model="Pump monitor",
            sw_version=(coordinator.data or {}).get("version"),
            configuration_url=entry.data.get("url"),
        )

    @property
    def data(self) -> dict[str, Any]:
        """The latest state of the building."""
        return self.coordinator.data or {}

    def pump(self, number: int) -> dict[str, Any]:
        """One pump's part of it, or nothing if it is not there."""
        return next((p for p in self.data.get("pumps", []) if p.get("number") == number), {})
