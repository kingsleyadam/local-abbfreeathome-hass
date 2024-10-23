"""Create ABB Free@Home light entities."""

from typing import Any

from abbfreeathome.devices.dimming_actuator import DimmingActuator
from abbfreeathome.freeathome import FreeAtHome

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
    LightEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.color import brightness_to_value, value_to_brightness

from .const import CONF_SERIAL, DOMAIN

BRIGHTNESS_SCALE = (1, 100)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up lights."""
    free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        FreeAtHomeLightEntity(light, sysap_serial_number=entry.data[CONF_SERIAL])
        for light in free_at_home.get_device_by_class(device_class=DimmingActuator)
    )


class FreeAtHomeLightEntity(LightEntity):
    """Defines a Free@Home light entity."""

    _attr_should_poll: bool = False

    def __init__(self, light: DimmingActuator, sysap_serial_number: str) -> None:
        """Initialize the light."""
        super().__init__()
        self._light = light
        self._sysap_serial_number = sysap_serial_number

        self.entity_description = LightEntityDescription(
            key="light",
            name=light.channel_name,
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._light.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._light.remove_callback(self.async_write_ha_state)

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._light.device_id)},
            "name": self._light.device_name,
            "manufacturer": "ABB busch-jaeger",
            "serial_number": self._light.device_id,
            "suggested_area": self._light.room_name,
            "via_device": (DOMAIN, self._sysap_serial_number),
        }

    @property
    def is_on(self) -> bool | None:
        """Return state of the light."""
        return self._light.state

    @property
    def brightness(self) -> int | None:
        """Return the current brightness."""
        return value_to_brightness(BRIGHTNESS_SCALE, self._light.brightness)

    @property
    def color_mode(self) -> str | None:
        """Return the color mode of the light."""
        return ColorMode.BRIGHTNESS

    @property
    def supported_color_modes(self) -> set[str] | None:
        """Flag supported color modes."""
        return {ColorMode.BRIGHTNESS}

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._light.device_id}_{self._light.channel_id}_light"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        if ATTR_BRIGHTNESS in kwargs:
            await self._light.set_brightness(
                brightness_to_value(BRIGHTNESS_SCALE, kwargs[ATTR_BRIGHTNESS])
            )
        else:
            await self._light.turn_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self._light.turn_off()

    async def async_update(self, **kwargs: Any) -> None:
        """Update the light state."""
        await self._light.refresh_state()
