"""Create ABB-free@home valve entities."""

from typing import Any

from abbfreeathome.devices.heating_actuator import HeatingActuator
from abbfreeathome.freeathome import FreeAtHome

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

from .const import CONF_SERIAL, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up valves."""
    free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        FreeAtHomeValveEntity(valve, sysap_serial_number=entry.data[CONF_SERIAL])
        for valve in free_at_home.get_devices_by_class(device_class=HeatingActuator)
    )


class FreeAtHomeValveEntity(ValveEntity):
    """Defines a free@home valve entity."""

    _attr_should_poll: bool = False

    def __init__(self, valve: HeatingActuator, sysap_serial_number: str) -> None:
        """Initialize the valve."""
        super().__init__()
        self._valve = valve
        self._sysap_serial_number = sysap_serial_number

        self.entity_description = ValveEntityDescription(
            key="HeatingActuatorValve",
            device_class=ValveDeviceClass.WATER,
            entity_registry_enabled_default=False,
            name=valve.channel_name,
            reports_position=True,
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._valve.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._valve.remove_callback(self.async_write_ha_state)

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._valve.device_id)},
            "name": self._valve.device_name,
            "manufacturer": "ABB busch-jaeger",
            "serial_number": self._valve.device_id,
            "suggested_area": self._valve.room_name,
            "via_device": (DOMAIN, self._sysap_serial_number),
        }

    @property
    def current_valve_position(self) -> int | None:
        """Return position of the valve."""
        return self._valve.position

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._valve.device_id}_{self._valve.channel_id}_valve"

    @property
    def supported_features(self) -> int | None:
        """Return supported features."""
        return ValveEntityFeature.SET_POSITION

    async def async_set_valve_position(self, position: int) -> None:
        """Move the valve to a specific position."""
        await self._valve.set_position(position)

    async def async_update(self, **kwargs: Any) -> None:
        """Update the valve state."""
        await self._valve.refresh_state()
