"""Adding a PitWatch building to Home Assistant.

Two things are asked for: where PitWatch is, and a token. The token is made on
PitWatch's profile page, under Home Assistant and other apps, and is for one
building, so one config entry is one building. Somebody with two buildings adds
the integration twice, with a token for each.
"""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any
from urllib.parse import urlparse

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_TOKEN, CONF_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .api import PitWatchAuthError, PitWatchClient, PitWatchConnectionError, PitWatchError
from .const import DEFAULT_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)

TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class PitWatchConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for PitWatch's address and a token, and check they work."""

    VERSION = 1

    async def _check(self, url: str, token: str) -> tuple[dict[str, Any] | None, str | None]:
        """Return the building this token opens, or why it does not."""
        client = PitWatchClient(async_get_clientsession(self.hass), url, token)
        try:
            return await client.state(), None
        except PitWatchAuthError:
            return None, "invalid_auth"
        except PitWatchConnectionError:
            return None, "cannot_connect"
        except PitWatchError:
            _LOGGER.exception("Unexpected answer from PitWatch")
            return None, "unknown"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the address and the token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            url = _normal(user_input[CONF_URL])
            token = user_input[CONF_API_TOKEN].strip()
            state, error = await self._check(url, token)
            if error:
                errors["base"] = error
            else:
                assert state is not None
                await self.async_set_unique_id(_unique_id(url, state))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=state["site"]["name"] or "PitWatch",
                    data={CONF_URL: url, CONF_API_TOKEN: token},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_URL, default=(user_input or {}).get(CONF_URL, DEFAULT_URL)
                    ): str,
                    vol.Required(CONF_API_TOKEN): TOKEN_SELECTOR,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start over with a new token: this one was revoked, or its owner lost access."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new token for the same building."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_API_TOKEN].strip()
            state, error = await self._check(entry.data[CONF_URL], token)
            if error:
                errors["base"] = error
            else:
                assert state is not None
                # The same building, or this is not a new token for it.
                await self.async_set_unique_id(_unique_id(entry.data[CONF_URL], state))
                self._abort_if_unique_id_mismatch(reason="wrong_building")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_TOKEN: token}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_TOKEN): TOKEN_SELECTOR}),
            description_placeholders={"building": entry.title},
            errors=errors,
        )


def _normal(url: str) -> str:
    """Give an address a scheme and no trailing slash.

    The bare pitwatch.app is the hosted service's short name and redirects to
    www. A redirect to another host is followed without the Authorization
    header, which is right of aiohttp and turns a good token into a refused
    one, so the address is stored as the one that does not redirect.
    """
    url = url.strip().rstrip("/")
    if "://" not in url:
        url = f"https://{url}"
    parts = urlparse(url)
    if parts.netloc == "pitwatch.app":
        url = parts._replace(netloc="www.pitwatch.app").geturl()
    return url


def _unique_id(url: str, state: dict[str, Any]) -> str:
    """One building on one PitWatch. The same building added twice is refused."""
    return f"{urlparse(url).netloc}_{state['site']['id']}"
