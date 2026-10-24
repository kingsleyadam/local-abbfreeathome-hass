"""Test ABB-free@home device status coordinator."""

from unittest.mock import AsyncMock, MagicMock

from abbfreeathome.exceptions import FreeAtHomeException
import pytest

from custom_components.abbfreeathome_ci.coordinator import (
    FreeAtHomeDeviceStatusCoordinator,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

# Shape of the /api/rest/configuration response, reduced to what is read here
CONFIGURATION = {
    "devices": {
        "ABB700CF0EFC": {
            "displayName": "Max",
            "unresponsive": False,
            "unresponsiveCounter": 0,
            "defect": False,
        },
        "ABB7F630796A": {
            "displayName": "Hobbyraum",
            "unresponsive": True,
            "unresponsiveCounter": 7,
            "defect": True,
        },
    }
}


def _coordinator(
    hass: HomeAssistant, mock_config_entry, configuration
) -> FreeAtHomeDeviceStatusCoordinator:
    """Build a coordinator over a mocked api."""
    free_at_home = MagicMock()
    free_at_home.api.get_configuration = AsyncMock(return_value=configuration)

    return FreeAtHomeDeviceStatusCoordinator(hass, mock_config_entry, free_at_home)


async def test_reads_the_device_status_flags(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test the status flags are read for every device."""
    mock_config_entry.add_to_hass(hass)
    coordinator = _coordinator(hass, mock_config_entry, CONFIGURATION)

    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert coordinator.data == {
        "ABB700CF0EFC": {
            "unresponsive": False,
            "unresponsive_counter": 0,
            "defect": False,
        },
        "ABB7F630796A": {
            "unresponsive": True,
            "unresponsive_counter": 7,
            "defect": True,
        },
    }


async def test_handles_a_configuration_without_devices(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test a response without a devices section does not raise."""
    mock_config_entry.add_to_hass(hass)
    coordinator = _coordinator(hass, mock_config_entry, {})

    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert coordinator.data == {}


async def test_handles_missing_flags(hass: HomeAssistant, mock_config_entry) -> None:
    """Test a device that reports none of the flags."""
    mock_config_entry.add_to_hass(hass)
    coordinator = _coordinator(
        hass, mock_config_entry, {"devices": {"ABB700CF0EFC": {}}}
    )

    await coordinator.async_refresh()

    assert coordinator.data == {
        "ABB700CF0EFC": {
            "unresponsive": False,
            "unresponsive_counter": 0,
            "defect": False,
        }
    }


async def test_api_error_becomes_update_failed(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test an api error is reported as a failed update, not as a crash."""
    mock_config_entry.add_to_hass(hass)

    free_at_home = MagicMock()
    free_at_home.api.get_configuration = AsyncMock(
        side_effect=FreeAtHomeException("boom")
    )
    coordinator = FreeAtHomeDeviceStatusCoordinator(
        hass, mock_config_entry, free_at_home
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    # Through the public refresh the failure is swallowed and flagged instead
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
