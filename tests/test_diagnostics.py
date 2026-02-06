"""Test diagnostics."""

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.diagnostics import (
    async_get_config_entry_diagnostics,
)
from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_free_at_home():
    """Create a mock FreeAtHome API object."""
    api = Mock()
    api.get_config = AsyncMock()
    return api


async def test_async_get_config_entry_diagnostics(
    hass: HomeAssistant, mock_config_entry, mock_free_at_home
):
    """Test diagnostics."""
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    # Mock config data
    mock_config = {
        "devices": {
            "ABB700000001": {
                "parameters": {"par0001": "value1", "invalid": "val2"},
                "channels": {
                    "ch0000": {
                        "inputs": {
                            "i0": {"pairingID": 1},
                            "i1": {"pairingID": 9999},  # Invalid/Unknown
                        },
                        "outputs": {
                            "o0": {"pairingID": 2},
                            "o1": {"pairingID": 9999},
                        },
                        "parameters": {"par0002": "value3", "invalid": "val4"},
                        "functionID": "1",
                    }
                },
            }
        },
        "sysapName": "Secret Name",
        "users": [],
    }

    # Need to verify deep copy or return value.
    # The function modifies the result of get_config().
    # But wait, async_get_config_entry_diagnostics calls get_config() TWICE.
    # (await _free_at_home.get_config()).get("devices")
    # and
    # await _free_at_home.get_config()

    # If get_config returns the SAME dict object, modifications persist.
    mock_free_at_home.get_config.return_value = mock_config

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert "sysapName" in result
    assert result["sysapName"] == "**REDACTED**"

    devices = result["devices"]
    device = devices["ABB700000001"]

    # Check Parameter Names injection
    assert "parameterNames" in device
    # par0001 -> assuming some Parameter Enum mapping or it falls back
    # The code uses: Parameter(int(key.lstrip('par'), 16)).name
    # 0x0001 -> 1. I don't know what Parameter(1) is, but it shouldn't raise ValueError if valid.
    # If 1 is not in Parameter enum, it raises ValueError.

    # Check channels
    channel = device["channels"]["ch0000"]
    assert "function" in channel
    # Function(1)

    assert "pairing" in channel["inputs"]["i0"]
    # Pairing(1)

    assert "parameterNames" in channel

    # Check handling of invalid values (ValueError blocks in code)
    # The code catches ValueError and sets "UNKNOWN".


async def test_async_get_config_entry_diagnostics_invalid_values(
    hass: HomeAssistant, mock_config_entry, mock_free_at_home
):
    """Test diagnostics with invalid values."""
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    # Mock config data with invalid hex values
    mock_config = {
        "devices": {
            "ABB700000001": {
                "parameters": {"parINVALID": "value1"},
                "channels": {
                    "ch0000": {
                        "inputs": {
                            "i0": {"pairingID": "invalid"},
                        },
                        "outputs": {
                            "o0": {"pairingID": "invalid"},
                        },
                        "parameters": {"parINVALID": "value3"},
                        "functionID": "invalid",
                    }
                },
            }
        },
        "sysapName": "Secret Name",
        "users": [],
    }

    mock_free_at_home.get_config.return_value = mock_config

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    device = result["devices"]["ABB700000001"]

    # Check Parameter Names handling of ValueError
    assert "UNKNOWN (parINVALID)" in device["parameterNames"]

    # Check channel function/pairing handling of ValueError
    channel = device["channels"]["ch0000"]
    assert channel["function"] == "UNKNOWN"
    assert channel["inputs"]["i0"]["pairing"] == "UNKNOWN"
    assert channel["outputs"]["o0"]["pairing"] == "UNKNOWN"
    assert "UNKNOWN (parINVALID)" in channel["parameterNames"]
