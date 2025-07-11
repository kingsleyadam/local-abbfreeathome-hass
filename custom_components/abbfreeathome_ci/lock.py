"""Create ABB-free@home lock entities."""

from typing import Any

from abbfreeathome import FreeAtHome
from abbfreeathome.channels.des_door_opener_actuator import DesDoorOpenerActuator

from homeassistant.components.lock import LockEntity, LockEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CREATE_SUBDEVICES, CONF_SERIAL, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up valves."""
    free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        FreeAtHomeLockEntity(
            channel,
            sysap_serial_number=entry.data[CONF_SERIAL],
            create_subdevices=entry.data[CONF_CREATE_SUBDEVICES],
        )
        for channel in free_at_home.get_channels_by_class(
            channel_class=DesDoorOpenerActuator
        )
    )


class FreeAtHomeLockEntity(LockEntity):
    """Defines a free@home lock entity."""

    _attr_should_poll: bool = False

    def __init__(
        self,
        channel: DesDoorOpenerActuator,
        sysap_serial_number: str,
        create_subdevices: bool,
    ) -> None:
        """Initialize the lock."""
        super().__init__()
        self._channel = channel
        self._sysap_serial_number = sysap_serial_number
        self._create_subdevices = create_subdevices

        self.entity_description = LockEntityDescription(
            key="DesDoorOpenerActuatorLock",
            name=channel.channel_name,
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._channel.register_callback(
            callback_attribute="state", callback=self.async_write_ha_state
        )

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._channel.remove_callback(
            callback_attribute="state", callback=self.async_write_ha_state
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        if self._create_subdevices and self._channel.device.is_multi_device:
            return {
                "identifiers": {
                    (
                        DOMAIN,
                        f"{self._channel.device_serial}_{self._channel.channel_id}",
                    )
                },
                "name": self._channel.channel_name,
                "manufacturer": "ABB Busch-Jaeger",
                "serial_number": f"{self._channel.device_serial}_{self._channel.channel_id}",
                "suggested_area": self._channel.room_name,
                "via_device": (DOMAIN, self._channel.device_serial),
            }

        return {
            "identifiers": {(DOMAIN, self._channel.device_serial)},
            "name": self._channel.device_name,
            "manufacturer": "ABB Busch-Jaeger",
            "serial_number": self._channel.device_serial,
            "suggested_area": self._channel.device.room_name,
            "via_device": (DOMAIN, self._sysap_serial_number),
        }

    @property
    def is_locked(self) -> bool | None:
        """Return if device is on."""
        return self._channel.state is False

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._channel.device_serial}_{self._channel.channel_id}_valve"

    async def async_lock(self, **kwargs):
        """Lock the device."""
        await self._channel.lock()

    async def async_unlock(self, **kwargs):
        """Unlock the device."""
        await self._channel.unlock()

    async def async_update(self, **kwargs: Any) -> None:
        """Update the lock state."""
        await self._channel.refresh_state()
