"""Test ABB-free@home helpers."""

import inspect
from unittest.mock import MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.helpers import async_get_via_device_kwargs
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr


def _mock_device_registry(*, supports_via_device_id: bool) -> MagicMock:
    """Return a mocked device registry mimicking an old or new HA core."""
    mock_device_registry = MagicMock()
    if supports_via_device_id:
        signature = inspect.signature(lambda *, via_device_id=None, **kwargs: None)
    else:
        signature = inspect.signature(lambda *, via_device=None, **kwargs: None)
    mock_device_registry.async_get_or_create.__signature__ = signature
    return mock_device_registry


async def test_via_device_kwargs_uses_via_device_id(hass: HomeAssistant) -> None:
    """Test the parent device id is used when the registry supports it."""
    mock_device_registry = _mock_device_registry(supports_via_device_id=True)

    with patch(
        "custom_components.abbfreeathome_ci.helpers.dr.async_get",
        return_value=mock_device_registry,
    ):
        result = async_get_via_device_kwargs(hass, "ENTRY123", "PARENT123")

    mock_device_registry.async_get_device_by_identifier.assert_called_once_with(
        (DOMAIN, "PARENT123"), "ENTRY123"
    )
    assert result == {
        "via_device_id": (
            mock_device_registry.async_get_device_by_identifier.return_value.id
        )
    }


async def test_via_device_kwargs_parent_not_registered(hass: HomeAssistant) -> None:
    """Test no link is returned when the parent device is not registered."""
    mock_device_registry = _mock_device_registry(supports_via_device_id=True)
    mock_device_registry.async_get_device_by_identifier.return_value = None

    with patch(
        "custom_components.abbfreeathome_ci.helpers.dr.async_get",
        return_value=mock_device_registry,
    ):
        result = async_get_via_device_kwargs(hass, "ENTRY123", "PARENT123")

    assert result == {}


async def test_via_device_kwargs_falls_back_to_via_device(
    hass: HomeAssistant,
) -> None:
    """Test via_device is used on older device registries."""
    mock_device_registry = _mock_device_registry(supports_via_device_id=False)

    with patch(
        "custom_components.abbfreeathome_ci.helpers.dr.async_get",
        return_value=mock_device_registry,
    ):
        result = async_get_via_device_kwargs(hass, "ENTRY123", "PARENT123")

    mock_device_registry.async_get_device_by_identifier.assert_not_called()
    assert result == {"via_device": (DOMAIN, "PARENT123")}


async def test_via_device_kwargs_links_devices_in_registry(
    hass: HomeAssistant,
) -> None:
    """Test the returned kwargs link devices with the installed HA core."""
    config_entry = MockConfigEntry(domain=DOMAIN)
    config_entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)

    parent_device = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, "PARENT123")},
    )
    child_device = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, "CHILD123")},
        **async_get_via_device_kwargs(hass, config_entry.entry_id, "PARENT123"),
    )

    assert child_device.via_device_id == parent_device.id
