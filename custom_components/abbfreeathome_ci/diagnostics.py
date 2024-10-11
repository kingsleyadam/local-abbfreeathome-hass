"""Diagnostics support for ABB Free@Home."""

from __future__ import annotations

from typing import Any

from abbfreeathome.freeathome import FreeAtHome

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {"latitude", "longitude", "sysapName", "uartSerialNumber"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    _free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]

    return async_redact_data(await _free_at_home.get_config(), TO_REDACT)
