"""Test ABB-free@home diagnostics."""

from unittest.mock import AsyncMock, MagicMock

from abbfreeathome import FreeAtHome

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.diagnostics import (
    async_get_config_entry_diagnostics,
)
from homeassistant.components.diagnostics import REDACTED
from homeassistant.core import HomeAssistant


def _configuration():
    """Return a SysAP configuration with known, unknown, and invalid IDs."""
    return {
        "sysapName": "My Home",
        "uartSerialNumber": "0123456789",
        "latitude": 52.52,
        "longitude": 13.405,
        "devices": {
            "ABB7F57FFFE12345": {
                "displayName": "Switch Actuator",
                "parameters": {"par0001": "1", "par0fff": "2", "parzz": "3"},
                "channels": {
                    "ch0000": {
                        "displayName": "Ceiling Light",
                        "functionID": "7",
                        "inputs": {
                            "idp0000": {"value": "1", "pairingID": 1},
                            "idp0001": {"value": "0", "pairingID": 9999},
                            "idp0002": {"value": "0"},
                        },
                        "outputs": {
                            "odp0000": {"value": "1", "pairingID": 256},
                            "odp0001": {"value": "0", "pairingID": 9999},
                        },
                        "parameters": {"par0001": "1", "par0fff": "2", "parzz": "3"},
                    },
                    "ch0001": {
                        "functionID": "fff",
                        "inputs": {},
                        "outputs": {},
                        "parameters": {},
                    },
                    "ch0002": {
                        "functionID": "zz",
                        "inputs": {},
                        "outputs": {},
                        "parameters": {},
                    },
                    "ch0003": {"displayName": "Unconfigured Channel"},
                },
            },
            "ABB7F57FFFE67890": {"displayName": "Device Without Channels"},
        },
    }


async def _async_get_diagnostics(hass, config_entry):
    """Return the diagnostics of a SysAP with the test configuration."""
    config_entry.add_to_hass(hass)

    # A real FreeAtHome object, so diagnostics use the library's cached config.
    api = MagicMock()
    api.get_configuration = AsyncMock(return_value=_configuration())
    hass.data[DOMAIN] = {config_entry.entry_id: FreeAtHome(api=api)}

    return await async_get_config_entry_diagnostics(hass, config_entry)


async def test_diagnostics_redacts_identifying_fields(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test location and identifying fields are redacted."""
    diagnostics = await _async_get_diagnostics(hass, mock_config_entry)

    assert diagnostics["sysapName"] == REDACTED
    assert diagnostics["uartSerialNumber"] == REDACTED
    assert diagnostics["latitude"] == REDACTED
    assert diagnostics["longitude"] == REDACTED
    assert diagnostics["devices"]["ABB7F57FFFE12345"]["displayName"] == (
        "Switch Actuator"
    )


async def test_diagnostics_adds_parameter_names(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test device and channel parameters get their names, or UNKNOWN."""
    diagnostics = await _async_get_diagnostics(hass, mock_config_entry)
    device = diagnostics["devices"]["ABB7F57FFFE12345"]

    expected = {
        "PID_LED_DAY_BRIGHTNESS (par0001)": "1",
        "UNKNOWN (par0fff)": "2",
        "UNKNOWN (parzz)": "3",
    }
    assert device["parameterNames"] == expected
    assert device["channels"]["ch0000"]["parameterNames"] == expected
    # The raw parameters are kept next to the names.
    assert device["parameters"] == {"par0001": "1", "par0fff": "2", "parzz": "3"}


async def test_diagnostics_adds_pairing_names(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test inputs and outputs get their pairing name, or UNKNOWN."""
    diagnostics = await _async_get_diagnostics(hass, mock_config_entry)
    channel = diagnostics["devices"]["ABB7F57FFFE12345"]["channels"]["ch0000"]

    assert channel["inputs"] == {
        "idp0000": {"pairing": "AL_SWITCH_ON_OFF", "pairingID": 1, "value": "1"},
        "idp0001": {"pairing": "UNKNOWN", "pairingID": 9999, "value": "0"},
        "idp0002": {"pairing": "UNKNOWN", "value": "0"},
    }
    assert channel["outputs"] == {
        "odp0000": {"pairing": "AL_INFO_ON_OFF", "pairingID": 256, "value": "1"},
        "odp0001": {"pairing": "UNKNOWN", "pairingID": 9999, "value": "0"},
    }


async def test_diagnostics_adds_function_names(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test channels get their function name, or UNKNOWN."""
    diagnostics = await _async_get_diagnostics(hass, mock_config_entry)
    channels = diagnostics["devices"]["ABB7F57FFFE12345"]["channels"]

    assert channels["ch0000"]["function"] == "FID_SWITCH_ACTUATOR"
    assert channels["ch0001"]["function"] == "UNKNOWN"
    assert channels["ch0002"]["function"] == "UNKNOWN"


async def test_diagnostics_sorts_channel_keys(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test channel, input, and output keys are sorted for readability."""
    diagnostics = await _async_get_diagnostics(hass, mock_config_entry)
    channel = diagnostics["devices"]["ABB7F57FFFE12345"]["channels"]["ch0000"]

    assert list(channel) == [
        "displayName",
        "function",
        "functionID",
        "inputs",
        "outputs",
        "parameterNames",
        "parameters",
    ]
    assert list(channel["inputs"]["idp0000"]) == ["pairing", "pairingID", "value"]
    assert list(channel["outputs"]["odp0000"]) == ["pairing", "pairingID", "value"]


async def test_diagnostics_tolerates_missing_keys(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test devices and channels without optional keys are still reported."""
    diagnostics = await _async_get_diagnostics(hass, mock_config_entry)
    devices = diagnostics["devices"]

    assert devices["ABB7F57FFFE67890"] == {
        "displayName": "Device Without Channels",
        "parameterNames": {},
    }
    assert devices["ABB7F57FFFE12345"]["channels"]["ch0003"] == {
        "displayName": "Unconfigured Channel",
        "function": "UNKNOWN",
        "parameterNames": {},
    }
