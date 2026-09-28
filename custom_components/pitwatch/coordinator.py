"""Keeping Home Assistant's picture of the building current.

PitWatch pushes. A websocket stream sends the whole state when it connects, then
a new state only when something in it changes, and every alert as it is raised
or cleared. So while the stream is up nothing is polled at all, and a pump that
starts appears here within a second.

When the stream is down this falls back to asking for the state once a minute,
and keeps trying to reconnect, backing off from five seconds to five minutes.
Alerts raised or cleared while it was down are fetched and announced when it
comes back, so an automation waiting on a flood alert does not miss one to a
dropped connection. What happened before Home Assistant started is not: an
alert from last Tuesday announced on a restart is noise, not news.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PitWatchAuthError, PitWatchClient, PitWatchError
from .const import (
    DOMAIN,
    EVENT_ALERT,
    FALLBACK_POLL,
    RECONNECT_MAX_S,
    RECONNECT_MIN_S,
)

_LOGGER = logging.getLogger(__name__)

AlertListener = Callable[[str, dict[str, Any]], None]


class PitWatchCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """The latest state of one building, pushed when it can be and polled when not."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: PitWatchClient) -> None:
        """Start out polling. The stream takes over once it connects."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=FALLBACK_POLL,
        )
        self.client = client
        self.connected = False
        self._alert_listeners: list[AlertListener] = []
        # Where the alert news has got to, for filling in a gap after a
        # reconnect. None until the first connection, which primes it rather
        # than replaying anything.
        self._newest_id: int | None = None
        self._cleared_seen: set[int] = set()

    async def _async_update_data(self) -> dict[str, Any]:
        """Ask for the state, which is what happens while the stream is down."""
        try:
            return await self.client.state()
        except PitWatchAuthError as error:
            raise ConfigEntryAuthFailed(str(error)) from error
        except PitWatchError as error:
            raise UpdateFailed(str(error)) from error

    @callback
    def async_add_alert_listener(self, listener: AlertListener) -> Callable[[], None]:
        """Be told about every alert raised or cleared. Returns the undo."""
        self._alert_listeners.append(listener)

        def remove() -> None:
            self._alert_listeners.remove(listener)

        return remove

    @callback
    def start(self) -> None:
        """Open the stream, and keep it open for as long as the entry is loaded."""
        self.config_entry.async_create_background_task(
            self.hass, self._keep_streaming(), f"{DOMAIN} stream {self.config_entry.entry_id}"
        )

    async def _keep_streaming(self) -> None:
        # Where things stand before the stream opens, so that anything raised
        # from here on arrives as news and nothing older does. Taken first
        # rather than once connected: an alert raised in between would
        # otherwise be both marked as seen and sent by the stream, and dropped.
        await self._prime()
        wait = RECONNECT_MIN_S
        while True:
            try:
                await self._stream_once()
                wait = RECONNECT_MIN_S
            except PitWatchAuthError:
                _LOGGER.warning("PitWatch refused the token; asking for a new one")
                self._went_down()
                self.config_entry.async_start_reauth(self.hass)
                return
            except PitWatchError as error:
                _LOGGER.debug("PitWatch stream ended: %s", error)
            self._went_down()
            # Straight back to polling, so the entities are current while this
            # waits to reconnect rather than a minute from now.
            await self.async_request_refresh()
            await asyncio.sleep(wait)
            wait = min(wait * 2, RECONNECT_MAX_S)

    async def _stream_once(self) -> None:
        first = True
        async for message in self.client.stream():
            kind = message.get("type")
            if kind == "snapshot":
                if first:
                    first = False
                    await self._came_up()
                self.async_set_updated_data(message["data"])
            elif kind == "alert":
                self._announce(message.get("event", ""), message.get("alert") or {})

    async def _prime(self) -> None:
        """Remember which alerts already happened, without announcing them."""
        try:
            recent = await self.client.alerts(limit=50)
        except PitWatchError as error:
            _LOGGER.debug("Could not fetch recent alerts to start from: %s", error)
            return
        self._cleared_seen.update(a["id"] for a in recent if a.get("cleared_at"))
        self._newest_id = max((a["id"] for a in recent), default=0)

    async def _came_up(self) -> None:
        """Stop polling now the stream is live, and fill in any gap in the alerts."""
        self.connected = True
        self.update_interval = None
        _LOGGER.debug("PitWatch stream connected")

        if self._newest_id is None:
            # Priming failed before the first connection. Do it now instead,
            # which can miss an alert raised in the last moment, and is still
            # better than announcing the whole history.
            await self._prime()
            return

        try:
            recent = await self.client.alerts(limit=50)
        except PitWatchError as error:
            _LOGGER.debug("Could not fetch recent alerts after reconnecting: %s", error)
            return
        # Oldest first, the order they happened in. Anything the stream also
        # sends is dropped by id in _announce, so nothing is said twice.
        for alert in reversed(recent):
            if alert["id"] > self._newest_id:
                self._announce("raised", alert)
            if alert.get("cleared_at"):
                self._announce("cleared", alert)

    @callback
    def _went_down(self) -> None:
        if self.connected:
            _LOGGER.debug("PitWatch stream disconnected; polling until it is back")
        self.connected = False
        self.update_interval = FALLBACK_POLL
        self.async_update_listeners()

    @callback
    def _announce(self, event: str, alert: dict[str, Any]) -> None:
        """Tell the event entity and the event bus about one alert."""
        if event not in ("raised", "cleared") or "id" not in alert:
            return
        if event == "raised":
            if self._newest_id is not None and alert["id"] <= self._newest_id:
                return
            self._newest_id = max(self._newest_id or 0, alert["id"])
        else:
            if alert["id"] in self._cleared_seen:
                return
            self._cleared_seen.add(alert["id"])
            # A clear for something raised before this connected moves the
            # raised mark past it as well, so a replay never raises it again.
            self._newest_id = max(self._newest_id or 0, alert["id"])

        site = (self.data or {}).get("site", {})
        self.hass.bus.async_fire(
            EVENT_ALERT,
            {
                "event": event,
                "site_id": site.get("id"),
                "site": site.get("name"),
                **alert_fields(alert, event),
            },
        )
        for listener in list(self._alert_listeners):
            listener(event, alert)


def alert_fields(alert: dict[str, Any], event: str) -> dict[str, Any]:
    """Pick out the parts of an alert worth handing to an automation."""
    return {
        "alert_id": alert.get("id"),
        "rule": alert.get("rule"),
        "title": alert.get("title"),
        "severity": alert.get("severity"),
        "pump": alert.get("pump"),
        # The sentence for this half of it: the alert's own when raised, its
        # all clear when cleared. PitWatch keeps no all clear for a few rules
        # whose clearing is not news, and then this falls back to the alert's.
        "message": (
            alert.get("cleared_message") or alert.get("message")
            if event == "cleared"
            else alert.get("message")
        ),
        "raised_at": alert.get("raised_at"),
        "cleared_at": alert.get("cleared_at"),
    }
