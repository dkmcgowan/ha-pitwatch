"""Shared fixtures for the PitWatch tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Generator
import copy
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitwatch.api import PitWatchAuthError
from custom_components.pitwatch.const import DOMAIN

URL = "https://www.pitwatch.app"
TOKEN = "pw_test-token"
UNIQUE_ID = "www.pitwatch.app_1"

# The shape PitWatch's /api/v1/state returns, with the values a quiet pit has.
SNAPSHOT: dict[str, Any] = {
    "api": 1,
    "version": "0.146.0",
    "site": {"id": 1, "name": "Test Building"},
    "pumps": [
        {
            "number": 1,
            "name": "Pump 1",
            "running": False,
            "current": 0.0,
            "usual_current": 15.2,
            "shut_off": False,
            "display": "LAG",
            "runs_today": 98,
            "last_start": "2026-09-28T12:00:00+00:00",
            "last_run_s": 11.8,
        },
        {
            "number": 2,
            "name": "Pump 2",
            "running": False,
            "current": 0.0,
            "usual_current": 17.1,
            "shut_off": False,
            "display": "LEAD",
            "runs_today": 97,
            "last_start": "2026-09-28T11:58:00+00:00",
            "last_run_s": 11.7,
        },
    ],
    "pit": {
        "high_water": False,
        "lead_float": False,
        "lag_float": False,
        "panel_alarm": False,
        "both_running": False,
    },
    "alerts": {"open": []},
    "devices": [
        {"key": "clamp1", "label": "Pump 1 clamp", "online": True},
        {"key": "health0", "label": "Inputs", "online": True},
    ],
    "rain": {
        "last_24h_mm": 7.6,
        "next_24h_mm": 2.1,
        "last_7d_mm": 44.5,
        "chance_next_24h": 80,
    },
    "panel_button": {"available": True, "allowed": False},
}


def alert(alert_id: int, **fields: Any) -> dict[str, Any]:
    """Build an alert the way /api/v1 describes one."""
    return {
        "id": alert_id,
        "rule": "high_water",
        "title": "High water",
        "severity": "critical",
        "pump": None,
        "message": "High water alert at Test Building.",
        "cleared_message": None,
        "raised_at": "2026-09-28T12:00:00+00:00",
        "cleared_at": None,
        **fields,
    }


class FakeStream:
    """Stands in for PitWatch's websocket. Tests feed it; it hands on."""

    def __init__(self) -> None:
        """Nothing sent yet."""
        self.queue: asyncio.Queue[Any] = asyncio.Queue()
        self.connections = 0

    def send(self, message: dict[str, Any]) -> None:
        """Push one message down the stream."""
        self.queue.put_nowait(message)

    def drop(self) -> None:
        """End this connection, as a network drop would."""
        self.queue.put_nowait(None)

    def refuse(self) -> None:
        """Close on the token, as PitWatch does when it is revoked."""
        self.queue.put_nowait(PitWatchAuthError("revoked"))

    async def __call__(self) -> AsyncIterator[dict[str, Any]]:
        """One connection's worth of messages."""
        self.connections += 1
        while True:
            item = await self.queue.get()
            if item is None:
                return
            if isinstance(item, Exception):
                raise item
            yield item


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in every test."""
    return enable_custom_integrations


@pytest.fixture
def snapshot() -> dict[str, Any]:
    """Give each test a fresh copy of the quiet pit to change."""
    return copy.deepcopy(SNAPSHOT)


@pytest.fixture
def stream() -> FakeStream:
    """Stand in for the websocket."""
    return FakeStream()


@pytest.fixture
def client(snapshot: dict[str, Any], stream: FakeStream) -> Generator[AsyncMock]:
    """PitWatchClient with every call answered here instead of over the network."""
    with patch("custom_components.pitwatch.PitWatchClient", autospec=True) as cls:
        instance = cls.return_value
        instance.state = AsyncMock(return_value=snapshot)
        instance.alerts = AsyncMock(return_value=[])
        instance.press = AsyncMock(return_value={"ok": True})
        instance.stream = stream
        yield instance


@pytest.fixture
def entry() -> MockConfigEntry:
    """Make a config entry for the test building."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test Building",
        unique_id=UNIQUE_ID,
        data={"url": URL, "api_token": TOKEN},
    )
