"""Create ABB-free@home light entities."""

from typing import Any

from abbfreeathome import FreeAtHome
from abbfreeathome.channels.dimming_actuator import (
    ColorTemperatureActuator,
    DimmingActuator,
)

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
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
        for light in free_at_home.get_channels_by_class(channel_class=DimmingActuator)
    )
    async_add_entities(
        FreeAtHomeLightEntity(light, sysap_serial_number=entry.data[CONF_SERIAL])
        for light in free_at_home.get_channels_by_class(
            channel_class=ColorTemperatureActuator
        )
    )


class FreeAtHomeLightEntity(LightEntity):
    """Defines a free@home light entity."""

    _attr_should_poll: bool = False
    _callback_attributes: list[str] = [
        "state",
        "brightness",
    ]

    def __init__(
        self,
        light: DimmingActuator | ColorTemperatureActuator,
        sysap_serial_number: str,
    ) -> None:
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
        for _callback_attribute in self._callback_attributes:
            self._light.register_callback(
                callback_attribute=_callback_attribute,
                callback=self.async_write_ha_state,
            )
        if hasattr(self._light, "color_temperature"):
            await self._light.register_callback(
                callback_attribute="color_temperature",
                callback=self.async_write_ha_state,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        for _callback_attribute in self._callback_attributes:
            self._light.remove_callback(
                callback_attribute=_callback_attribute,
                callback=self.async_write_ha_state,
            )
        if hasattr(self._light, "color_temperature"):
            await self._light.remove_callback(
                callback_attribute="color_temperature",
                callback=self.async_write_ha_state,
            )

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._light.device_serial)},
            "name": self._light.device_name,
            "manufacturer": "ABB busch-jaeger",
            "serial_number": self._light.device_serial,
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
    def color_temp_kelvin(self) -> int | None:
        """Return the color temperature in Kelvin."""
        return map_range(
            self._light.color_temperature,
            0,
            100,
            self._light.color_temperature_warmest,
            self._light.color_temperature_coolest,
        )

    @property
    def color_mode(self) -> str | None:
        """Return the color mode of the light."""
        if hasattr(self._light, "color_temperature"):
            return ColorMode.COLOR_TEMP
        return ColorMode.BRIGHTNESS

    @property
    def supported_color_modes(self) -> set[str] | None:
        """Flag supported color modes."""
        _color_modes = {ColorMode.BRIGHTNESS}

        if hasattr(self._light, "color_temperature"):
            _color_modes.add(ColorMode.COLOR_TEMP)

        return _color_modes

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._light.device_serial}_{self._light.channel_id}_light"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        if ATTR_BRIGHTNESS in kwargs:
            await self._light.set_brightness(
                int(brightness_to_value(BRIGHTNESS_SCALE, kwargs[ATTR_BRIGHTNESS]))
            )
            return

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            if hasattr(self._light, "color_temperature"):
                await self._light.set_color_temperature(
                    map_range(
                        kwargs[ATTR_COLOR_TEMP_KELVIN],
                        self._light.color_temperature_warmest,
                        self._light.color_temperature_coolest,
                        0,
                        100,
                    )
                )
            return

        await self._light.turn_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self._light.turn_off()

    async def async_update(self, **kwargs: Any) -> None:
        """Update the light state."""
        await self._light.refresh_state()


def map_range(
    value: int,
    from_min: int,
    from_max: int,
    to_min: int,
    to_max: int,
) -> int:
    """Map a value from one range to another."""
    return (value - from_min) * (to_max - to_min) / (from_max - from_min) + to_min
