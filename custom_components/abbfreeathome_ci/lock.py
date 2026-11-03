"""Create ABB-free@home lock entities."""

from typing import Any

from abbfreeathome.channels.des_door_opener_actuator import DesDoorOpenerActuator

from homeassistant.components.lock import LockEntity, LockEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CREATE_SUBDEVICES, CONF_SERIAL, DOMAIN
from .entity import ChannelGetter, FreeAtHomeEntity, async_setup_platform_entities
from .helpers import AnyDeviceInfo, async_get_sub_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up locks."""

    def build_entities(get_channels: ChannelGetter) -> list[FreeAtHomeLockEntity]:
        return [
            FreeAtHomeLockEntity(
                channel,
                sysap_serial_number=entry.data[CONF_SERIAL],
                create_subdevices=entry.data[CONF_CREATE_SUBDEVICES],
            )
            for channel in get_channels(DesDoorOpenerActuator)
        ]

    async_setup_platform_entities(hass, entry, async_add_entities, build_entities)


class FreeAtHomeLockEntity(FreeAtHomeEntity, LockEntity):
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
        await super().async_added_to_hass()
        self._channel.register_callback(
            callback_attribute="state", callback=self.async_write_ha_state
        )

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._channel.remove_callback(
            callback_attribute="state", callback=self.async_write_ha_state
        )

    @property
    def device_info(self) -> AnyDeviceInfo:
        """Information about this entity/device."""
        if self._create_subdevices and self._channel.device.is_multi_device:
            return async_get_sub_device_info(
                self.hass, self.platform.config_entry.entry_id, self._channel
            )

        return DeviceInfo(identifiers={(DOMAIN, self._channel.device_serial)})

    @property
    def is_locked(self) -> bool | None:
        """Return if the door is locked."""
        if self._channel.state is None:
            return None
        return not self._channel.state

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
