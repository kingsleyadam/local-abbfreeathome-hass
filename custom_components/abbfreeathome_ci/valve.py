"""Create ABB-free@home valve entities."""

from typing import Any

from abbfreeathome import FreeAtHome
from abbfreeathome.channels.heating_actuator import HeatingActuator

from homeassistant.components.valve import (
    ValveDeviceClass,
    ValveEntity,
    ValveEntityDescription,
    ValveEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CREATE_SUBDEVICES, CONF_SERIAL, DOMAIN, MANUFACTURER


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up valves."""
    free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        FreeAtHomeValveEntity(
            channel,
            sysap_serial_number=entry.data[CONF_SERIAL],
            create_subdevices=entry.data[CONF_CREATE_SUBDEVICES],
        )
        for channel in free_at_home.get_channels_by_class(channel_class=HeatingActuator)
    )


class FreeAtHomeValveEntity(ValveEntity):
    """Defines a free@home valve entity."""

    _attr_should_poll: bool = False

    def __init__(
        self,
        channel: HeatingActuator,
        sysap_serial_number: str,
        create_subdevices: bool,
    ) -> None:
        """Initialize the valve."""
        super().__init__()
        self._channel = channel
        self._sysap_serial_number = sysap_serial_number
        self._create_subdevices = create_subdevices

        self.entity_description = ValveEntityDescription(
            key="HeatingActuatorValve",
            device_class=ValveDeviceClass.WATER,
            entity_registry_enabled_default=False,
            name=channel.channel_name,
            reports_position=True,
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._channel.register_callback(
            callback_attribute="position", callback=self.async_write_ha_state
        )

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._channel.remove_callback(
            callback_attribute="position", callback=self.async_write_ha_state
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        if self._create_subdevices and self._channel.device.is_multi_device:
            return DeviceInfo(
                identifiers={
                    (
                        DOMAIN,
                        f"{self._channel.device_serial}_{self._channel.channel_id}",
                    )
                },
                name=f"{self._channel.device_name} ({self._channel.channel_id})",
                manufacturer=MANUFACTURER,
                serial_number=f"{self._channel.device_serial}_{self._channel.channel_id}",
                hw_version=f"{self._channel.device.device_id} (sub)",
                suggested_area=self._channel.room_name,
                via_device=(DOMAIN, self._channel.device_serial),
            )

        return DeviceInfo(identifiers={(DOMAIN, self._channel.device_serial)})

    @property
    def current_valve_position(self) -> int | None:
        """Return position of the valve."""
        return self._channel.position

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._channel.device_serial}_{self._channel.channel_id}_valve"

    @property
    def supported_features(self) -> int | None:
        """Return supported features."""
        return ValveEntityFeature.SET_POSITION

    async def async_set_valve_position(self, position: int) -> None:
        """Move the valve to a specific position."""
        await self._channel.set_position(position)

    async def async_update(self, **kwargs: Any) -> None:
        """Update the valve state."""
        await self._channel.refresh_state()
