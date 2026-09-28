"""The panel's own button, pressed from Home Assistant.

Only there if the building has the button wired to PitWatch and the token was
made able to press it. Silence stops the horn; reset clears the alarm, which is
what lets a pump the controller held out after an overload back into use. It
does not, and cannot, reset an overload relay: that is a separate device, and
somebody should look at a motor that overloaded before it runs again.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PitWatchConfigEntry
from .api import PitWatchError
from .coordinator import PitWatchCoordinator
from .entity import PitWatchEntity

BUTTONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(key="silence", translation_key="silence", icon="mdi:bell-off"),
    ButtonEntityDescription(key="reset", translation_key="reset", icon="mdi:restart-alert"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PitWatchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the two presses, if this token may make them."""
    coordinator = entry.runtime_data
    button = (coordinator.data or {}).get("panel_button", {})
    if not (button.get("available") and button.get("allowed")):
        return
    async_add_entities(PanelButton(coordinator, description) for description in BUTTONS)


class PanelButton(PitWatchEntity, ButtonEntity):
    """One of the two presses the panel knows."""

    def __init__(
        self, coordinator: PitWatchCoordinator, description: ButtonEntityDescription
    ) -> None:
        """Tie the press to this building."""
        super().__init__(coordinator, f"panel_{description.key}")
        self.entity_description = description

    async def async_press(self) -> None:
        """Press it, through PitWatch."""
        try:
            await self.coordinator.client.press(self.entity_description.key)
        except PitWatchError as error:
            raise HomeAssistantError(f"PitWatch could not press the button: {error}") from error
