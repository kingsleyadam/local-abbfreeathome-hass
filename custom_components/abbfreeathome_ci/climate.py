"""Create ABB-free@home climate entities."""

from typing import Any

from abbfreeathome.devices.room_temperature_controller import RoomTemperatureController
from abbfreeathome.freeathome import FreeAtHome

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
)
from homeassistant.components.climate.const import HVACAction, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SERIAL, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate devices."""
    free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        FreeAtHomeClimateEntity(climate, sysap_serial_number=entry.data[CONF_SERIAL])
        for climate in free_at_home.get_devices_by_class(
            device_class=RoomTemperatureController
        )
    )


class FreeAtHomeClimateEntity(ClimateEntity):
    """Defines a free@home climate entity."""

    _attr_should_poll: bool = False
    _callback_attributes: list[str] = [
        "state",
        "current_temperature",
        "heating",
        "cooling",
        "target_temperature",
        "eco_mode",
    ]

    def __init__(
        self, climate: RoomTemperatureController, sysap_serial_number: str
    ) -> None:
        """Initialize the climate device."""
        super().__init__()
        self._climate = climate
        self._sysap_serial_number = sysap_serial_number

        self.entity_description = ClimateEntityDescription(
            key="RoomTemperatureController",
            name=climate.channel_name,
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        for _callback_attribute in self._callback_attributes:
            self._climate.register_callback(
                callback_attribute=_callback_attribute,
                callback=self.async_write_ha_state,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        for _callback_attribute in self._callback_attributes:
            self._climate.remove_callback(
                callback_attribute=_callback_attribute,
                callback=self.async_write_ha_state,
            )

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._climate.device_id)},
            "name": self._climate.device_name,
            "manufacturer": "ABB busch-jaeger",
            "serial_number": self._climate.device_id,
            "suggested_area": self._climate.room_name,
            "via_device": (DOMAIN, self._sysap_serial_number),
        }

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._climate.device_id}_{self._climate.channel_id}_climate"

    @property
    def temperature_unit(self) -> str | None:
        """Return the temperature unit."""
        return UnitOfTemperature.CELSIUS

    @property
    def target_temperature_step(self) -> float | None:
        """Return the possible target temperature steps."""
        return 0.5

    @property
    def max_temp(self) -> float | None:
        """Return the max temperature."""
        return float(35)

    @property
    def min_temp(self) -> float | None:
        """Return the min temperature."""
        return float(7)

    @property
    def extra_state_attributes(self) -> dict[Any] | None:
        """Return device specific state attributes."""
        return {"heating": self._climate.heating, "cooling": self._climate.cooling}

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._climate.current_temperature

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current mode."""
        if not self._climate.state:
            return HVACMode.OFF
        return HVACMode.HEAT_COOL

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current action."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        if self._climate.heating > self._climate.cooling:
            return HVACAction.HEATING
        if self._climate.cooling > self._climate.heating:
            return HVACAction.COOLING

        return HVACAction.IDLE

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        if self.hvac_mode == HVACMode.OFF:
            return None
        return self._climate.target_temperature

    @property
    def supported_features(self) -> int | None:
        """Return the list of supported features."""
        return (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.PRESET_MODE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
        )

    @property
    def hvac_modes(self) -> list | None:
        """Return the list of available hvac modes."""
        return [HVACMode.HEAT_COOL, HVACMode.OFF]

    @property
    def preset_modes(self) -> list | None:
        """Return the list of available presets."""
        return ["none", "eco"]

    @property
    def preset_mode(self) -> str | None:
        """Return the current mode."""
        if self._climate.eco_mode:
            return "eco"
        return None

    @property
    def state(self) -> bool | None:
        """Return the current operation."""
        if not self._climate.state:
            return HVACMode.OFF
        return HVACMode.HEAT_COOL

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        """Set new target operation mode."""
        if hvac_mode == HVACMode.HEAT_COOL:
            await self._climate.turn_on()

        if hvac_mode == HVACMode.OFF:
            await self._climate.turn_off()

    async def async_turn_on(self) -> None:
        """Turn the device on."""
        await self._climate.turn_on()

    async def async_turn_off(self) -> None:
        """Turn the device off."""
        await self._climate.turn_off()

    async def async_set_preset_mode(self, preset_mode) -> None:
        """Set new preset mode."""
        if preset_mode == "eco":
            await self._climate.eco_on()
        else:
            await self._climate.eco_off()

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        await self._climate.set_temperature(temperature)

    async def async_update(self, **kwargs: Any) -> None:
        """Update the switch state."""
        await self._climate.refresh_state()
