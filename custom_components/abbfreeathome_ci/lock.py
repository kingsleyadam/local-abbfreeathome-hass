"""Create ABB-free@home lock entities."""

from typing import Any

from abbfreeathome.devices.des_door_opener_actuator import DesDoorOpenerActuator
from abbfreeathome.freeathome import FreeAtHome

from homeassistant.components.lock import LockEntity, LockEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SERIAL, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up valves."""
    free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        FreeAtHomeLockEntity(lock, sysap_serial_number=entry.data[CONF_SERIAL])
        for lock in free_at_home.get_devices_by_class(
            device_class=DesDoorOpenerActuator
        )
    )


class FreeAtHomeLockEntity(LockEntity):
    """Defines a free@home lock entity."""

    _attr_should_poll: bool = False

    def __init__(self, lock: DesDoorOpenerActuator, sysap_serial_number: str) -> None:
        """Initialize the valve."""
        super().__init__()
        self._lock = lock
        self._sysap_serial_number = sysap_serial_number

        self.entity_description = LockEntityDescription(
            key="DesDoorOpenerActuatorLock",
            name=lock.channel_name,
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._lock.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._lock.remove_callback(self.async_write_ha_state)

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._lock.device_id)},
            "name": self._lock.device_name,
            "manufacturer": "ABB busch-jaeger",
            "serial_number": self._lock.device_id,
            "suggested_area": self._lock.room_name,
            "via_device": (DOMAIN, self._sysap_serial_number),
        }

    @property
    def is_locked(self) -> bool | None:
        """Return if device is on."""
        return self._lock.state is False

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._lock.device_id}_{self._lock.channel_id}_valve"

    async def async_lock(self, **kwargs):
        """Lock the device."""
        await self._lock.lock()

    async def async_unlock(self, **kwargs):
        """Unlock the device."""
        await self._lock.unlock()

    async def async_update(self, **kwargs: Any) -> None:
        """Update the lock state."""
        await self._valve.refresh_state()
