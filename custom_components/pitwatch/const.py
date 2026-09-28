"""Constants for the PitWatch integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "pitwatch"
MANUFACTURER = "PitWatch"

DEFAULT_URL = "https://www.pitwatch.app"

# Fired on the Home Assistant event bus for every alert raised or cleared, as
# well as through the alerts event entity. The bus event is what an automation
# written in YAML reaches for; the entity is what the UI shows.
EVENT_ALERT = f"{DOMAIN}_alert"

# How often to ask for the state while the live stream is down. While it is up
# nothing is polled at all: PitWatch pushes every change as it happens.
FALLBACK_POLL = timedelta(seconds=60)

# Reconnecting after the stream drops, doubling from the first to the last.
RECONNECT_MIN_S = 5
RECONNECT_MAX_S = 300

# PitWatch sends a keepalive every 25 seconds on a quiet stream, so a stream
# that says nothing for this long is dead rather than quiet.
STREAM_SILENCE_S = 90
