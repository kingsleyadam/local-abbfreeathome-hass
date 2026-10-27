"""Create ABB-free@home climate entities."""

from typing import Any

from abbfreeathome import FreeAtHome
from abbfreeathome.channels.room_temperature_controller import (
    RadiatorActuator,
    RoomTemperatureController,
)

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

from .const import CONF_CREATE_SUBDEVICES, CONF_SERIAL, DOMAIN, MANUFACTURER
from .helpers import async_get_via_device_kwargs


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate devices."""
    free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        FreeAtHomeClimateEntity(
            channel,
            sysap_serial_number=entry.data[CONF_SERIAL],
            create_subdevices=entry.data[CONF_CREATE_SUBDEVICES],
        )
        for channel in free_at_home.get_channels_by_class(
            channel_class=RoomTemperatureController
        )
    )

    async_add_entities(
        FreeAtHomeRadiatorClimateEntity(
            channel,
            sysap_serial_number=entry.data[CONF_SERIAL],
            create_subdevices=entry.data[CONF_CREATE_SUBDEVICES],
        )
        for channel in free_at_home.get_channels_by_class(
            channel_class=RadiatorActuator
        )
    )


class FreeAtHomeClimateEntity(ClimateEntity):
    """Defines a free@home climate entity."""

    _attr_should_poll: bool = False
    _entity_description_key: str = "RoomTemperatureController"
    _callback_attributes: list[str] = [
        "state",
        "current_temperature",
        "heating",
        "cooling",
        "target_temperature",
        "eco_mode",
    ]

    def __init__(
        self,
        channel: RoomTemperatureController,
        sysap_serial_number: str,
        create_subdevices: bool,
    ) -> None:
        """Initialize the climate device."""
        super().__init__()
        self._channel = channel
        self._sysap_serial_number = sysap_serial_number
        self._create_subdevices = create_subdevices

        self.entity_description = ClimateEntityDescription(
            key=self._entity_description_key,
            name=channel.channel_name,
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        for _callback_attribute in self._callback_attributes:
            self._channel.register_callback(
                callback_attribute=_callback_attribute,
                callback=self.async_write_ha_state,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        for _callback_attribute in self._callback_attributes:
            self._channel.remove_callback(
                callback_attribute=_callback_attribute,
                callback=self.async_write_ha_state,
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
                **async_get_via_device_kwargs(
                    self.hass,
                    self.platform.config_entry.entry_id,
                    self._channel.device_serial,
                ),
            )

        return DeviceInfo(identifiers={(DOMAIN, self._channel.device_serial)})

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._channel.device_serial}_{self._channel.channel_id}_climate"

    @property
    def native_temperature_unit(self) -> str:
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
        return {"heating": self._channel.heating, "cooling": self._channel.cooling}

    @property
    def native_current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._channel.current_temperature

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current mode."""
        if not self._channel.state:
            return HVACMode.OFF
        return HVACMode.HEAT_COOL

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current action."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        if self._channel.heating > self._channel.cooling:
            return HVACAction.HEATING
        if self._channel.cooling > self._channel.heating:
            return HVACAction.COOLING

        return HVACAction.IDLE

    @property
    def native_target_temperature(self) -> float | None:
        """Return the target temperature."""
        if self.hvac_mode == HVACMode.OFF:
            return None
        return self._channel.target_temperature

    if not hasattr(ClimateEntity, "native_temperature_unit"):
        # HA Core 2026.11 introduced native_*; legacy names are removed in 2027.11.
        # Keep these aliases only for HA versions older than 2026.11.
        temperature_unit = native_temperature_unit
        current_temperature = native_current_temperature
        target_temperature = native_target_temperature

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
        if self._channel.eco_mode:
            return "eco"
        return None

    @property
    def state(self) -> bool | None:
        """Return the current operation."""
        if not self._channel.state:
            return HVACMode.OFF
        return HVACMode.HEAT_COOL

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        """Set new target operation mode."""
        if hvac_mode == HVACMode.HEAT_COOL:
            await self._channel.turn_on()

        if hvac_mode == HVACMode.OFF:
            await self._channel.turn_off()

    async def async_turn_on(self) -> None:
        """Turn the device on."""
        await self._channel.turn_on()

    async def async_turn_off(self) -> None:
        """Turn the device off."""
        await self._channel.turn_off()

    async def async_set_preset_mode(self, preset_mode) -> None:
        """Set new preset mode."""
        if preset_mode == "eco":
            await self._channel.eco_on()
        else:
            await self._channel.eco_off()

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        await self._channel.set_temperature(temperature)

    async def async_update(self, **kwargs: Any) -> None:
        """Update the switch state."""
        await self._channel.refresh_state()


class FreeAtHomeRadiatorClimateEntity(FreeAtHomeClimateEntity):
    """Defines a free@home radiator thermostat climate entity.

    A radiator thermostat only heats, so it offers HEAT instead of HEAT_COOL
    and derives its action from the thermostat's own heating state.
    """

    _entity_description_key: str = "RadiatorActuator"
    # Same as the room temperature controller, plus the radiator heating state
    _callback_attributes: list[str] = [
        "state",
        "current_temperature",
        "heating",
        "cooling",
        "target_temperature",
        "eco_mode",
        "heating_active",
    ]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return device specific state attributes."""
        return {
            "heating": self._channel.heating,
            "heating_active": self._channel.heating_active,
        }

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current mode."""
        if not self._channel.state:
            return HVACMode.OFF
        return HVACMode.HEAT

    @property
    def hvac_modes(self) -> list | None:
        """Return the list of available hvac modes."""
        return [HVACMode.HEAT, HVACMode.OFF]

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current action."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if self._channel.heating_active:
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def state(self) -> HVACMode | None:
        """Return the current operation."""
        return self.hvac_mode

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        """Set new target operation mode."""
        if hvac_mode == HVACMode.HEAT:
            await self._channel.turn_on()

        if hvac_mode == HVACMode.OFF:
            await self._channel.turn_off()
