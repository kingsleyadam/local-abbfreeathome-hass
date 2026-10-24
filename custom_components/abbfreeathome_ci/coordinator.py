"""Coordinator for ABB-free@home device status flags."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from abbfreeathome import FreeAtHome
from abbfreeathome.exceptions import FreeAtHomeException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=15)


class FreeAtHomeDeviceStatusCoordinator(
    DataUpdateCoordinator[dict[str, dict[str, Any]]]
):
    """Keeps the per device status flags of the SysAP up to date.

    The free@home websocket only pushes datapoint changes, so a device turning
    unresponsive is never signalled to the channel objects. These flags are
    therefore polled from the configuration instead.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        free_at_home: FreeAtHome,
    ) -> None:
        """Initialize the device status coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_device_status",
            update_interval=SCAN_INTERVAL,
        )
        self._free_at_home = free_at_home

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch the status flags of every device from the api."""
        try:
            _config = await self._free_at_home.api.get_configuration()
        except FreeAtHomeException as exc:
            raise UpdateFailed(f"Could not fetch the device status: {exc}") from exc

        return {
            _serial: {
                "unresponsive": bool(_data.get("unresponsive")),
                "unresponsive_counter": int(_data.get("unresponsiveCounter") or 0),
                "defect": bool(_data.get("defect")),
            }
            for _serial, _data in (_config.get("devices") or {}).items()
        }
