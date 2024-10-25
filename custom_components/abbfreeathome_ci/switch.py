"""Create ABB Free@Home switch entities."""

from typing import Any

from abbfreeathome.devices.switch_actuator import SwitchActuator
from abbfreeathome.freeathome import FreeAtHome

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
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
    """Set up switches."""
    free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        FreeAtHomeSwitchEntity(switch, sysap_serial_number=entry.data[CONF_SERIAL])
        for switch in free_at_home.get_devices_by_class(device_class=SwitchActuator)
    )


class FreeAtHomeSwitchEntity(SwitchEntity):
    """Defines a Free@Home switch entity."""

    _attr_should_poll: bool = False

    def __init__(self, switch: SwitchActuator, sysap_serial_number: str) -> None:
        """Initialize the switch."""
        super().__init__()
        self._switch = switch
        self._sysap_serial_number = sysap_serial_number

        self.entity_description = SwitchEntityDescription(
            key="switch",
            device_class=SwitchDeviceClass.SWITCH,
            name=switch.channel_name,
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._switch.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._switch.remove_callback(self.async_write_ha_state)

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._switch.device_id)},
            "name": self._switch.device_name,
            "manufacturer": "ABB busch-jaeger",
            "serial_number": self._switch.device_id,
            "suggested_area": self._switch.room_name,
            "via_device": (DOMAIN, self._sysap_serial_number),
        }

    @property
    def is_on(self) -> bool | None:
        """Return state of the switch."""
        return self._switch.state

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._switch.device_id}_{self._switch.channel_id}_switch"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._switch.turn_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._switch.turn_off()

    async def async_update(self, **kwargs: Any) -> None:
        """Update the switch state."""
        await self._switch.refresh_state()
