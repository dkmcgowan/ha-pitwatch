"""Adding a building, and giving it a new token."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.pitwatch.const import DOMAIN

from .conftest import SNAPSHOT, TOKEN, UNIQUE_ID, URL

STATE_URL = f"{URL}/api/v1/state"


@pytest.fixture(autouse=True)
def no_setup() -> Generator[AsyncMock]:
    """Stop a finished flow from setting the entry up for real.

    These tests are about the flow. Setting up is tested in test_init, and
    here it would open a stream to an address nothing answers.
    """
    with patch("custom_components.pitwatch.async_setup_entry", return_value=True) as setup:
        yield setup


async def _start(hass: HomeAssistant) -> str:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    return result["flow_id"]


async def test_a_good_token_adds_the_building(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(STATE_URL, json=SNAPSHOT)

    result = await hass.config_entries.flow.async_configure(
        await _start(hass), {"url": URL, "api_token": f"  {TOKEN}  "}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test Building"
    assert result["data"] == {"url": URL, "api_token": TOKEN}
    assert result["result"].unique_id == UNIQUE_ID
    # The token went as a bearer token and nowhere else.
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == f"Bearer {TOKEN}"


async def test_the_short_address_is_stored_as_the_one_that_does_not_redirect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Store the short address as the one that does not redirect.

    pitwatch.app redirects to www, and a redirect to another host drops the
    Authorization header, so a good token would come back refused.
    """
    aioclient_mock.get(STATE_URL, json=SNAPSHOT)

    result = await hass.config_entries.flow.async_configure(
        await _start(hass), {"url": "pitwatch.app/", "api_token": TOKEN}
    )

    assert result["data"]["url"] == URL


async def test_a_refused_token_says_so(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(STATE_URL, status=401, json={"detail": "A valid token is needed"})

    result = await hass.config_entries.flow.async_configure(
        await _start(hass), {"url": URL, "api_token": "pw_wrong"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_an_unreachable_pitwatch_says_so(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(STATE_URL, exc=TimeoutError())

    result = await hass.config_entries.flow.async_configure(
        await _start(hass), {"url": URL, "api_token": TOKEN}
    )

    assert result["errors"] == {"base": "cannot_connect"}


async def test_the_same_building_twice_is_refused(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    aioclient_mock.get(STATE_URL, json=SNAPSHOT)

    result = await hass.config_entries.flow.async_configure(
        await _start(hass), {"url": URL, "api_token": "pw_another"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_a_new_token_for_the_same_building_is_taken(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    aioclient_mock.get(STATE_URL, json=SNAPSHOT)

    flow = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"api_token": "pw_fresh"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["api_token"] == "pw_fresh"


async def test_a_token_for_another_building_is_not_a_new_token(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    aioclient_mock.get(STATE_URL, json={**SNAPSHOT, "site": {"id": 2, "name": "Next door"}})

    flow = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"api_token": "pw_next_door"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_building"
    assert entry.data["api_token"] == TOKEN
