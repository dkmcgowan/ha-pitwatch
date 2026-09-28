"""A client for PitWatch's API.

PitWatch serves a small versioned API under ``/api/v1`` for software other than
its own web pages. Everything here is authenticated with a bearer token made on
the PitWatch profile page. A token belongs to one building, reads only unless
it was made able to press the panel button, and can be revoked there at any
time, at which point every call here starts failing with PitWatchAuthError.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
import logging
from typing import Any

import aiohttp

from .const import STREAM_SILENCE_S

_LOGGER = logging.getLogger(__name__)

# How long a plain request may take. The stream has its own rule.
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)


class PitWatchError(Exception):
    """Something went wrong talking to PitWatch."""


class PitWatchAuthError(PitWatchError):
    """The token was refused: wrong, revoked, or its owner lost access."""


class PitWatchConnectionError(PitWatchError):
    """PitWatch could not be reached, or answered with something unusable."""


class PitWatchClient:
    """Talks to one PitWatch building through one token."""

    def __init__(self, session: aiohttp.ClientSession, url: str, token: str) -> None:
        """Keep the session, the address and the token."""
        self._session = session
        self._url = url.rstrip("/")
        self._token = token

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            async with self._session.request(
                method,
                f"{self._url}{path}",
                headers=self._headers,
                timeout=REQUEST_TIMEOUT,
                **kwargs,
            ) as response:
                if response.status in (401, 403):
                    detail = await _detail(response)
                    if response.status == 401:
                        raise PitWatchAuthError(detail or "PitWatch refused the token")
                    raise PitWatchError(detail or "PitWatch said no")
                if response.status >= 400:
                    raise PitWatchConnectionError(
                        f"PitWatch answered {response.status}: {await _detail(response)}"
                    )
                return await response.json()
        except (aiohttp.ClientError, TimeoutError) as error:
            raise PitWatchConnectionError(f"Could not reach PitWatch: {error}") from error
        except ValueError as error:
            raise PitWatchConnectionError(
                "PitWatch answered with something that is not JSON"
            ) from error

    async def state(self) -> dict[str, Any]:
        """Return the building as it is now."""
        return await self._request("GET", "/api/v1/state")

    async def alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent alerts, newest first."""
        body = await self._request("GET", "/api/v1/alerts", params={"limit": limit})
        return body.get("alerts", [])

    async def press(self, action: str) -> dict[str, Any]:
        """Press the panel's button: ``silence`` or ``reset``."""
        return await self._request("POST", "/api/v1/panel/press", json={"action": action})

    async def stream(self) -> AsyncIterator[dict[str, Any]]:
        """Every message PitWatch pushes, for as long as the connection lasts.

        Ends when the connection ends, for whatever reason. Raises
        PitWatchAuthError if the token is refused, at the handshake or later
        when it is revoked, so the caller can stop reconnecting and ask for a
        new one.
        """
        url = self._url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        try:
            async with self._session.ws_connect(
                f"{url}/api/v1/stream", headers=self._headers, heartbeat=None
            ) as socket:
                while True:
                    message = await socket.receive(timeout=STREAM_SILENCE_S)
                    if message.type == aiohttp.WSMsgType.TEXT:
                        yield message.json()
                    elif message.type in (
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSING,
                        aiohttp.WSMsgType.CLOSED,
                    ):
                        # 1008 is PitWatch's "you may not": the token was
                        # revoked, or its owner lost access, while connected.
                        if socket.close_code == 1008 or message.data == 1008:
                            raise PitWatchAuthError("PitWatch closed the stream on the token")
                        return
                    elif message.type == aiohttp.WSMsgType.ERROR:
                        raise PitWatchConnectionError(f"The stream failed: {socket.exception()}")
        except aiohttp.WSServerHandshakeError as error:
            # Refused before the socket opened, which a websocket reports as
            # the HTTP status of the handshake.
            if error.status in (401, 403):
                raise PitWatchAuthError("PitWatch refused the token") from error
            raise PitWatchConnectionError(f"The stream was refused: {error.status}") from error
        except (aiohttp.ClientError, TimeoutError) as error:
            raise PitWatchConnectionError(f"The stream dropped: {error!r}") from error


async def _detail(response: aiohttp.ClientResponse) -> str:
    """Return what PitWatch said about a refusal, if anything readable."""
    try:
        body = await response.json()
    except (aiohttp.ContentTypeError, ValueError):
        return ""
    return str(body.get("detail", "")) if isinstance(body, dict) else ""
