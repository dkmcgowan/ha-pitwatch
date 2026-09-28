"""Binary sensors: what is on in the pit right now.

Every one is PitWatch's reading rather than a wire. The contacts arrive
debounced, a pump that overloaded stays shut off until the panel lets it back
in, and the panel alarm is read through its pulse instead of flashing here
twice a second the way the contact does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PitWatchConfigEntry
from .coordinator import PitWatchCoordinator
from .entity import PitWatchEntity

# The alerts that mean somebody should look. Info is news, not a problem.
ATTENTION = ("warning", "critical")


@dataclass(frozen=True, kw_only=True)
class PitDescription(BinarySensorEntityDescription):
    """A binary sensor read off the pit's part of the state."""

    field: str


PIT: tuple[PitDescription, ...] = (
    PitDescription(
        key="high_water",
        translation_key="high_water",
        field="high_water",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    PitDescription(key="lead_float", translation_key="lead_float", field="lead_float"),
    PitDescription(key="lag_float", translation_key="lag_float", field="lag_float"),
    PitDescription(
        key="panel_alarm",
        translation_key="panel_alarm",
        field="panel_alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    PitDescription(
        key="both_running",
        translation_key="both_running",
        field="both_running",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
)


@dataclass(frozen=True, kw_only=True)
class PumpDescription(BinarySensorEntityDescription):
    """A binary sensor about one pump, named after it."""

    field: str


PUMP: tuple[PumpDescription, ...] = (
    PumpDescription(
        key="running",
        translation_key="pump_running",
        field="running",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    PumpDescription(
        key="shut_off",
        translation_key="pump_shut_off",
        field="shut_off",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PitWatchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the pit, the pumps, the alerts and the connections."""
    coordinator = entry.runtime_data
    data = coordinator.data or {}
    entities: list[BinarySensorEntity] = [
        PitBinarySensor(coordinator, description) for description in PIT
    ]
    for pump in data.get("pumps", []):
        entities.extend(
            PumpBinarySensor(coordinator, pump["number"], pump["name"], description)
            for description in PUMP
        )
    entities.append(NeedsAttention(coordinator))
    entities.extend(
        DeviceOnline(coordinator, device["key"], device["label"])
        for device in data.get("devices", [])
    )
    entities.append(LiveConnection(coordinator))
    async_add_entities(entities)


class PitBinarySensor(PitWatchEntity, BinarySensorEntity):
    """High water, the floats, the panel alarm, both pumps on at once."""

    entity_description: PitDescription

    def __init__(self, coordinator: PitWatchCoordinator, description: PitDescription) -> None:
        """Tie the description to this building."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """On, off, or unknown when PitWatch has not been told yet."""
        return self.data.get("pit", {}).get(self.entity_description.field)


class PumpBinarySensor(PitWatchEntity, BinarySensorEntity):
    """Whether one pump is running, and whether it has shut itself off."""

    entity_description: PumpDescription

    def __init__(
        self,
        coordinator: PitWatchCoordinator,
        number: int,
        name: str,
        description: PumpDescription,
    ) -> None:
        """Name it after the pump, the way PitWatch does."""
        super().__init__(coordinator, f"pump{number}_{description.key}")
        self.entity_description = description
        self._number = number
        # The pump's own name, from PitWatch, into the translated name.
        self._attr_translation_placeholders = {"pump": name}

    @property
    def is_on(self) -> bool | None:
        """On, off, or unknown."""
        return self.pump(self._number).get(self.entity_description.field)


class NeedsAttention(PitWatchEntity, BinarySensorEntity):
    """On while any warning or critical alert is open.

    The one sensor to put on a dashboard or hang an automation off if nothing
    else: it is on whenever PitWatch has something a person should look at,
    and the open alerts are listed on it with their plain sentences.
    """

    _attr_translation_key = "needs_attention"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: PitWatchCoordinator) -> None:
        """One per building."""
        super().__init__(coordinator, "needs_attention")

    def _open(self) -> list[dict[str, Any]]:
        return [
            alert
            for alert in self.data.get("alerts", {}).get("open", [])
            if alert.get("severity") in ATTENTION
        ]

    @property
    def is_on(self) -> bool:
        """On while anything needs looking at."""
        return bool(self._open())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The open alerts, in the words PitWatch sends them in."""
        return {
            "alerts": [
                {
                    "title": alert.get("title"),
                    "message": alert.get("message"),
                    "severity": alert.get("severity"),
                    "raised_at": alert.get("raised_at"),
                }
                for alert in self._open()
            ]
        }


class DeviceOnline(PitWatchEntity, BinarySensorEntity):
    """Whether PitWatch can hear one of the devices at the building."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: PitWatchCoordinator, key: str, label: str) -> None:
        """Named the way PitWatch's dashboard names it."""
        super().__init__(coordinator, f"device_{key}")
        self._key = key
        self._attr_name = label

    @property
    def is_on(self) -> bool | None:
        """Online, offline, or unknown if it has gone from PitWatch's list."""
        for device in self.data.get("devices", []):
            if device.get("key") == self._key:
                return bool(device.get("online"))
        return None


class LiveConnection(PitWatchEntity, BinarySensorEntity):
    """Whether PitWatch's live stream is connected.

    Off means Home Assistant is asking once a minute instead of being told
    straight away, which is still working, only slower.
    """

    _attr_translation_key = "live_connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: PitWatchCoordinator) -> None:
        """One per building."""
        super().__init__(coordinator, "live_connection")

    @property
    def available(self) -> bool:
        """Always: whether the connection is up is the thing being reported."""
        return True

    @property
    def is_on(self) -> bool:
        """Connected or not."""
        return self.coordinator.connected
