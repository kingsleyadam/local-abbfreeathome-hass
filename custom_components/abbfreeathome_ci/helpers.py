"""Helpers for the ABB-free@home integration."""

from __future__ import annotations

import inspect
from typing import Any

from abbfreeathome.channels.base import Base

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, MANUFACTURER

# ChildDeviceInfo was added in HA 2026.9. The alias is evaluated lazily, so it
# can be used in annotations on older versions too.
type AnyDeviceInfo = DeviceInfo | dr.ChildDeviceInfo


@callback
def async_get_via_device_kwargs(
    hass: HomeAssistant, config_entry_id: str, parent_serial: str
) -> dict[str, Any]:
    """Return the keyword argument linking a device to its parent device.

    HA 2026.8 deprecated via_device in favor of via_device_id (removal
    planned for 2027.8.0). Since this integration supports a wide range of
    HA versions, detect at runtime which parameter is available instead of
    hard-coding a version cutoff - this keeps working unchanged before,
    during and after the transition.

    The parent device is looked up with async_get_device_by_identifier, which
    was added in the same HA version as via_device_id and replaces the
    deprecated async_get_device.
    """
    device_registry = dr.async_get(hass)

    # compat: homeassistant<2026.8 - via_device_id replaced via_device
    if (
        "via_device_id"
        not in inspect.signature(device_registry.async_get_or_create).parameters
    ):
        return {"via_device": (DOMAIN, parent_serial)}

    parent_device = device_registry.async_get_device_by_identifier(
        (DOMAIN, parent_serial), config_entry_id
    )
    if parent_device is None:
        return {}

    return {"via_device_id": parent_device.id}


@callback
def async_get_sub_device_info(
    hass: HomeAssistant, config_entry_id: str, channel: Base
) -> AnyDeviceInfo:
    """Return the device info of the sub-device for a channel of a multi-device.

    HA 2026.9 added child devices, which model the parts of one physical
    device. Existing sub-devices with the same identifiers are converted to
    child devices in place, keeping their device id. Home Assistant shows the
    parent device name in front of a child's name, so a child device is named
    after its channel only.

    Older HA versions have no child devices; there the sub-device is a device
    of its own, linked to the physical device with via_device or via_device_id.
    """
    sub_device_serial = f"{channel.device_serial}_{channel.channel_id}"

    # A child device needs a registered parent; without one, fall back to an
    # unlinked sub-device.
    # compat: homeassistant<2026.9 - drop the ChildDeviceInfo check; child devices were added
    if hasattr(dr, "ChildDeviceInfo") and (
        parent_device := dr.async_get(hass).async_get_device_by_identifier(
            (DOMAIN, channel.device_serial), config_entry_id
        )
    ):
        return dr.ChildDeviceInfo(
            identifiers={(DOMAIN, sub_device_serial)},
            name=channel.channel_id,
            parent_device_id=parent_device.id,
            suggested_area=channel.room_name,
        )

    return DeviceInfo(
        identifiers={(DOMAIN, sub_device_serial)},
        name=f"{channel.device_name} ({channel.channel_id})",
        manufacturer=MANUFACTURER,
        serial_number=sub_device_serial,
        hw_version=f"{channel.device.device_id} (sub)",
        suggested_area=channel.room_name,
        **async_get_via_device_kwargs(hass, config_entry_id, channel.device_serial),
    )
