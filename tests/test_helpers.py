"""Test ABB-free@home helpers."""

import inspect
from unittest.mock import MagicMock, Mock, patch

import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN, MANUFACTURER
from custom_components.abbfreeathome_ci.helpers import (
    async_get_sub_device_info,
    async_get_via_device_kwargs,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .common import MockConfigEntry


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


def _sub_device_channel() -> Mock:
    """Return a channel of a multi-device."""
    return Mock(
        device_serial="ABB700000001",
        channel_id="ch0001",
        device_name="Actuator",
        room_name="Kitchen",
        device=Mock(device_id="B002"),
    )


async def test_sub_device_info_uses_child_device(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test a child device named after its channel is used when supported."""
    mock_child_device_info = MagicMock()
    monkeypatch.setattr(dr, "ChildDeviceInfo", mock_child_device_info, raising=False)
    mock_device_registry = MagicMock()

    with patch(
        "custom_components.abbfreeathome_ci.helpers.dr.async_get",
        return_value=mock_device_registry,
    ):
        result = async_get_sub_device_info(hass, "ENTRY123", _sub_device_channel())

    mock_device_registry.async_get_device_by_identifier.assert_called_once_with(
        (DOMAIN, "ABB700000001"), "ENTRY123"
    )
    mock_child_device_info.assert_called_once_with(
        identifiers={(DOMAIN, "ABB700000001_ch0001")},
        name="ch0001",
        parent_device_id=(
            mock_device_registry.async_get_device_by_identifier.return_value.id
        ),
        suggested_area="Kitchen",
    )
    assert result is mock_child_device_info.return_value


@pytest.mark.parametrize(
    ("child_devices_supported", "parent_registered"),
    [(False, True), (True, False)],
)
async def test_sub_device_info_falls_back_to_linked_device(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    child_devices_supported: bool,
    parent_registered: bool,
) -> None:
    """Test a device linked to its parent without child devices or a parent."""
    mock_child_device_info = MagicMock()
    if child_devices_supported:
        monkeypatch.setattr(
            dr, "ChildDeviceInfo", mock_child_device_info, raising=False
        )
    else:
        monkeypatch.delattr(dr, "ChildDeviceInfo", raising=False)
    mock_device_registry = MagicMock()
    if not parent_registered:
        mock_device_registry.async_get_device_by_identifier.return_value = None

    with (
        patch(
            "custom_components.abbfreeathome_ci.helpers.dr.async_get",
            return_value=mock_device_registry,
        ),
        patch(
            "custom_components.abbfreeathome_ci.helpers.async_get_via_device_kwargs",
            return_value={"via_device_id": "parent_device_id"},
        ) as mock_via_device_kwargs,
    ):
        result = async_get_sub_device_info(hass, "ENTRY123", _sub_device_channel())

    mock_child_device_info.assert_not_called()
    mock_via_device_kwargs.assert_called_once_with(hass, "ENTRY123", "ABB700000001")
    assert result == {
        "identifiers": {(DOMAIN, "ABB700000001_ch0001")},
        "name": "Actuator (ch0001)",
        "manufacturer": MANUFACTURER,
        "serial_number": "ABB700000001_ch0001",
        "hw_version": "B002 (sub)",
        "suggested_area": "Kitchen",
        "via_device_id": "parent_device_id",
    }
