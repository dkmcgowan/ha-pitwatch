"""Sensors: the numbers, per pump and for the building."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfPrecipitationDepth,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PitWatchConfigEntry
from .coordinator import PitWatchCoordinator
from .entity import PitWatchEntity

# The words on the pump controller's own display, which PitWatch copies so
# somebody who has stood in front of the panel can read it without being
# taught. Lower case here because Home Assistant wants its enum states that way.
DISPLAY = ["lead", "lag", "on", "error"]


@dataclass(frozen=True, kw_only=True)
class PumpDescription(SensorEntityDescription):
    """A sensor about one pump, named after it."""

    value: Callable[[dict[str, Any]], Any]


PUMP: tuple[PumpDescription, ...] = (
    PumpDescription(
        key="current",
        translation_key="pump_current",
        value=lambda pump: pump.get("current"),
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    PumpDescription(
        key="runs_today",
        translation_key="pump_runs_today",
        value=lambda pump: pump.get("runs_today"),
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
    ),
    PumpDescription(
        key="last_run",
        translation_key="pump_last_run",
        value=lambda pump: pump.get("last_run_s"),
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=1,
    ),
    PumpDescription(
        key="display",
        translation_key="pump_display",
        value=lambda pump: (pump.get("display") or "").lower() or None,
        device_class=SensorDeviceClass.ENUM,
        options=DISPLAY,
        icon="mdi:monitor",
    ),
    PumpDescription(
        key="usual_current",
        translation_key="pump_usual_current",
        value=lambda pump: pump.get("usual_current"),
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


@dataclass(frozen=True, kw_only=True)
class SiteDescription(SensorEntityDescription):
    """A sensor about the building as a whole."""

    value: Callable[[dict[str, Any]], Any]


def _rain(field: str) -> Callable[[dict[str, Any]], Any]:
    return lambda data: (data.get("rain") or {}).get(field)


SITE: tuple[SiteDescription, ...] = (
    SiteDescription(
        key="open_alerts",
        translation_key="open_alerts",
        value=lambda data: len(data.get("alerts", {}).get("open", [])),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SiteDescription(
        key="rain_last_24h",
        translation_key="rain_last_24h",
        value=_rain("last_24h_mm"),
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        suggested_display_precision=1,
    ),
    SiteDescription(
        key="rain_next_24h",
        translation_key="rain_next_24h",
        value=_rain("next_24h_mm"),
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        suggested_display_precision=1,
    ),
    SiteDescription(
        key="rain_last_7d",
        translation_key="rain_last_7d",
        value=_rain("last_7d_mm"),
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        suggested_display_precision=1,
    ),
    SiteDescription(
        key="rain_chance",
        translation_key="rain_chance",
        value=_rain("chance_next_24h"),
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:weather-rainy",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PitWatchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the pump numbers and the building's."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [SiteSensor(coordinator, description) for description in SITE]
    for pump in (coordinator.data or {}).get("pumps", []):
        entities.extend(
            PumpSensor(coordinator, pump["number"], pump["name"], description)
            for description in PUMP
        )
    async_add_entities(entities)


class PumpSensor(PitWatchEntity, SensorEntity):
    """One number about one pump."""

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
    def native_value(self) -> Any:
        """The number, or unknown when PitWatch has none."""
        return self.entity_description.value(self.pump(self._number))


class SiteSensor(PitWatchEntity, SensorEntity):
    """One number about the building."""

    entity_description: SiteDescription

    def __init__(self, coordinator: PitWatchCoordinator, description: SiteDescription) -> None:
        """Tie the description to this building."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """The number, or unknown when PitWatch has none."""
        return self.entity_description.value(self.data)
