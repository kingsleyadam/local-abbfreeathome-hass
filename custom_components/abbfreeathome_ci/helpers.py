"""Helpers for the ABB-free@home integration."""

from __future__ import annotations

import inspect
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN


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
