"""Create ABB-free@home valve entities."""

from typing import Any

from abbfreeathome import FreeAtHome
from abbfreeathome.channels.valve_actuator import (
    CoolingActuator,
    HeatingActuator,
    HeatingCoolingActuator,
)

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

VALVE_DESCRIPTIONS = {
    "HeatingActuatorValve": {
        "channel_class": HeatingActuator,
        "position_attribute": "position",
        "set_position_method": "set_position",
        "callback_attributes": ["position"],
        "entity_description_kwargs": {
            "device_class": ValveDeviceClass.WATER,
            "translation_key": "heating_actuator",
        },
    },
    "CoolingActuatorValve": {
        "channel_class": CoolingActuator,
        "position_attribute": "position",
        "set_position_method": "set_position",
        "callback_attributes": ["position"],
        "entity_description_kwargs": {
            "device_class": ValveDeviceClass.WATER,
            "translation_key": "cooling_actuator",
        },
    },
    "HeatingCoolingActuatorHeatingValve": {
        "channel_class": HeatingCoolingActuator,
        "position_attribute": "heating_position",
        "set_position_method": "set_heating_position",
        "callback_attributes": ["heating_position"],
        "entity_description_kwargs": {
            "device_class": ValveDeviceClass.WATER,
            "translation_key": "heating_actuator",
        },
    },
    "HeatingCoolingActuatorCoolingValve": {
        "channel_class": HeatingCoolingActuator,
        "position_attribute": "cooling_position",
        "set_position_method": "set_cooling_position",
        "callback_attributes": ["cooling_position"],
        "entity_description_kwargs": {
            "device_class": ValveDeviceClass.WATER,
            "translation_key": "cooling_actuator",
        },
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up valves."""
    free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]

    for key, description in VALVE_DESCRIPTIONS.items():
        async_add_entities(
            FreeAtHomeValveEntity(
                channel,
                position_attribute=description.get("position_attribute"),
                set_position_method=description.get("set_position_method"),
                callback_attributes=description.get("callback_attributes"),
                entity_description_kwargs={"key": key}
                | description.get("entity_description_kwargs"),
                sysap_serial_number=entry.data[CONF_SERIAL],
                create_subdevices=entry.data[CONF_CREATE_SUBDEVICES],
            )
            for channel in free_at_home.get_channels_by_class(
                channel_class=description.get("channel_class")
            )
        )


class FreeAtHomeValveEntity(ValveEntity):
    """Defines a free@home valve entity."""

    _attr_should_poll: bool = False

    def __init__(
        self,
        channel: HeatingActuator | CoolingActuator | HeatingCoolingActuator,
        position_attribute: str,
        set_position_method: str,
        callback_attributes: list[str],
        entity_description_kwargs: dict[str, Any],
        sysap_serial_number: str,
        create_subdevices: bool,
    ) -> None:
        """Initialize the valve."""
        super().__init__()
        self._channel = channel
        self._position_attribute = position_attribute
        self._set_position_method = set_position_method
        self._callback_attributes = callback_attributes
        self._sysap_serial_number = sysap_serial_number
        self._create_subdevices = create_subdevices

        self.entity_description = ValveEntityDescription(
            has_entity_name=True,
            name=channel.channel_name,
            entity_registry_enabled_default=False,
            reports_position=True,
            **entity_description_kwargs,
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        for callback_attribute in self._callback_attributes:
            self._channel.register_callback(
                callback_attribute=callback_attribute,
                callback=self.async_write_ha_state,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        for callback_attribute in self._callback_attributes:
            self._channel.remove_callback(
                callback_attribute=callback_attribute,
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
                via_device=(DOMAIN, self._channel.device_serial),
            )

        return DeviceInfo(identifiers={(DOMAIN, self._channel.device_serial)})

    @property
    def current_valve_position(self) -> int | None:
        """Return position of the valve."""
        return getattr(self._channel, self._position_attribute)

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        # Maintain backward compatibility: use "_valve" for HeatingActuatorValve
        if self.entity_description.key == "HeatingActuatorValve":
            return f"{self._channel.device_serial}_{self._channel.channel_id}_valve"
        return f"{self._channel.device_serial}_{self._channel.channel_id}_{self.entity_description.key}"

    @property
    def supported_features(self) -> int | None:
        """Return supported features."""
        return ValveEntityFeature.SET_POSITION

    async def async_set_valve_position(self, position: int) -> None:
        """Move the valve to a specific position."""
        await getattr(self._channel, self._set_position_method)(position)

    async def async_update(self, **kwargs: Any) -> None:
        """Update the valve state."""
        await self._channel.refresh_state()
