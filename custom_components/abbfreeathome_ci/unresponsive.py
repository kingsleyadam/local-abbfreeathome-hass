"""Repair issues for unresponsive ABB-free@home devices."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from functools import partial
import logging

from abbfreeathome.device import Device

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later

from .const import DOMAIN, UNRESPONSIVE_REPAIR_DELAY

_LOGGER = logging.getLogger(__name__)

DATA_UNRESPONSIVE_TRACKERS = f"{DOMAIN}_unresponsive_trackers"


@callback
def async_get_unresponsive_tracker(
    hass: HomeAssistant, entry_id: str
) -> UnresponsiveDeviceTracker | None:
    """Return the tracker of a config entry, if repairs are enabled."""
    return hass.data.get(DATA_UNRESPONSIVE_TRACKERS, {}).get(entry_id)


class UnresponsiveDeviceTracker:
    """Create a repair issue for devices that stay unresponsive.

    An issue is created once a device has been unresponsive for
    UNRESPONSIVE_REPAIR_DELAY and removed as soon as it responds again,
    is removed, or the config entry is unloaded.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the tracker and register it for the config entry."""
        self._hass = hass
        self._entry = entry
        self._callbacks: dict[str, tuple[Device, Callable[[], None]]] = {}
        self._timers: dict[str, CALLBACK_TYPE] = {}

        hass.data.setdefault(DATA_UNRESPONSIVE_TRACKERS, {})[entry.entry_id] = self
        entry.async_on_unload(self.async_shutdown)

    def _issue_id(self, device_serial: str) -> str:
        return f"unresponsive_{self._entry.entry_id}_{device_serial}"

    @callback
    def async_track(self, device: Device) -> None:
        """Watch a device and report its current state."""
        if device.device_serial in self._callbacks:
            return

        _callback = partial(self._async_update, device)
        device.register_unresponsive_callback(_callback)
        self._callbacks[device.device_serial] = (device, _callback)
        self._async_update(device)

    @callback
    def async_untrack(self, device_serials: Iterable[str]) -> None:
        """Stop watching devices and remove their repair issues."""
        for _serial in device_serials:
            if (_tracked := self._callbacks.pop(_serial, None)) is None:
                continue
            _device, _callback = _tracked
            _device.remove_unresponsive_callback(_callback)
            self._async_cancel_timer(_serial)
            ir.async_delete_issue(self._hass, DOMAIN, self._issue_id(_serial))

    @callback
    def async_shutdown(self) -> None:
        """Stop watching all devices and remove all repair issues."""
        self.async_untrack(list(self._callbacks))
        self._hass.data[DATA_UNRESPONSIVE_TRACKERS].pop(self._entry.entry_id, None)

    @callback
    def _async_update(self, device: Device) -> None:
        _serial = device.device_serial
        if not device.unresponsive:
            self._async_cancel_timer(_serial)
            ir.async_delete_issue(self._hass, DOMAIN, self._issue_id(_serial))
            return

        if _serial not in self._timers:
            self._timers[_serial] = async_call_later(
                self._hass,
                UNRESPONSIVE_REPAIR_DELAY,
                partial(self._async_create_issue, device),
            )

    @callback
    def _async_cancel_timer(self, device_serial: str) -> None:
        if (_cancel := self._timers.pop(device_serial, None)) is not None:
            _cancel()

    @callback
    def _async_create_issue(self, device: Device, _now: datetime) -> None:
        self._timers.pop(device.device_serial, None)
        _LOGGER.debug("Creating repair issue for device %s", device.device_serial)
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            self._issue_id(device.device_serial),
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=(
                "virtual_device_unresponsive"
                if device.is_virtual
                else "device_unresponsive"
            ),
            translation_placeholders={
                "name": device.display_name,
                "serial": device.device_serial,
            },
        )
