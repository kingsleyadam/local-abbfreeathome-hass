"""Create ABB-free@home switch entities."""

from typing import Any

from abbfreeathome.devices.switch_actuator import SwitchActuator
from abbfreeathome.devices.switch_sensor import DimmingSensor, SwitchSensor
from abbfreeathome.devices.virtual.virtual_brightness_sensor import (
    VirtualBrightnessSensor,
)
from abbfreeathome.devices.virtual.virtual_rain_sensor import VirtualRainSensor
from abbfreeathome.devices.virtual.virtual_switch_actuator import VirtualSwitchActuator
from abbfreeathome.devices.virtual.virtual_temperature_sensor import (
    VirtualTemperatureSensor,
)
from abbfreeathome.devices.virtual.virtual_wind_sensor import VirtualWindSensor
from abbfreeathome.devices.virtual.virtual_window_door_sensor import (
    VirtualWindowDoorSensor,
)
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

SWITCH_DESCRIPTIONS = {
    "DimmingSensorLed": {
        "device_class": DimmingSensor,
        "value_attribute": "led",
        "entity_description_kwargs": {
            "device_class": SwitchDeviceClass.SWITCH,
        },
    },
    "SwitchActuator": {
        "device_class": SwitchActuator,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": SwitchDeviceClass.SWITCH,
        },
    },
    "SwitchSensorLed": {
        "device_class": SwitchSensor,
        "value_attribute": "led",
        "entity_description_kwargs": {
            "device_class": SwitchDeviceClass.SWITCH,
        },
    },
    "VirtualBrightessSensorAlarm": {
        "device_class": VirtualBrightnessSensor,
        "value_attribute": "alarm",
        "entity_description_kwargs": {
            "device_class": SwitchDeviceClass.SWITCH,
            "translation_key": "virtual_brightness_sensor",
        },
    },
    "VirtualRainSensorAlarm": {
        "device_class": VirtualRainSensor,
        "value_attribute": "alarm",
        "entity_description_kwargs": {
            "device_class": SwitchDeviceClass.SWITCH,
            "translation_key": "virtual_rain_sensor",
        },
    },
    "VirtualSwitchActuatorOnOff": {
        "device_class": VirtualSwitchActuator,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": SwitchDeviceClass.SWITCH,
        },
    },
    "VirtualWindSensorAlarm": {
        "device_class": VirtualWindSensor,
        "value_attribute": "alarm",
        "entity_description_kwargs": {
            "device_class": SwitchDeviceClass.SWITCH,
            "translation_key": "virtual_wind_sensor",
        },
    },
    "VirtualWindowDoorSensorOnOff": {
        "device_class": VirtualWindowDoorSensor,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": SwitchDeviceClass.SWITCH,
        },
    },
    "VirtualTemperatureSensorAlarm": {
        "device_class": VirtualTemperatureSensor,
        "value_attribute": "alarm",
        "entity_description_kwargs": {
            "device_class": SwitchDeviceClass.SWITCH,
            "translation_key": "virtual_temperature_sensor",
        },
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches."""
    free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]

    for key, description in SWITCH_DESCRIPTIONS.items():
        async_add_entities(
            FreeAtHomeSwitchEntity(
                device,
                value_attribute=description.get("value_attribute"),
                entity_description_kwargs={"key": key}
                | description.get("entity_description_kwargs"),
                sysap_serial_number=entry.data[CONF_SERIAL],
            )
            for device in free_at_home.get_devices_by_class(
                device_class=description.get("device_class")
            )
            if getattr(device, description.get("value_attribute")) is not None
        )


class FreeAtHomeSwitchEntity(SwitchEntity):
    """Defines a free@home switch entity."""

    _attr_should_poll: bool = False

    def __init__(
        self,
        device: DimmingSensor
        | SwitchActuator
        | SwitchSensor
        | VirtualBrightnessSensor
        | VirtualSwitchActuator
        | VirtualWindowDoorSensor,
        value_attribute: str,
        entity_description_kwargs: dict[str:Any],
        sysap_serial_number: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__()
        self._device = device
        self._value_attribute = value_attribute
        self._sysap_serial_number = sysap_serial_number

        self.entity_description = SwitchEntityDescription(
            has_entity_name=True,
            name=device.channel_name,
            translation_placeholders={"channel_id": device.channel_id},
            **entity_description_kwargs,
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._device.register_callback(
            callback_attribute=self._value_attribute, callback=self.async_write_ha_state
        )

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._device.remove_callback(
            callback_attribute=self._value_attribute, callback=self.async_write_ha_state
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._device.device_id)},
            "name": self._device.device_name,
            "manufacturer": "ABB busch-jaeger",
            "serial_number": self._device.device_id,
            "suggested_area": self._device.room_name,
            "via_device": (DOMAIN, self._sysap_serial_number),
        }

    @property
    def translation_key(self):
        """Return the translation key to translate the entity's name and states.

        if the device_name and channel_name are the same, then this sensor is not the
        main feature of the device and should have it's name translated.
        """
        _translation_key = None
        if hasattr(self, "_attr_translation_key"):
            _translation_key = self._attr_translation_key
        if hasattr(self, "entity_description"):
            _translation_key = self.entity_description.translation_key

        if self._device.channel_name == self._device.device_name:
            return _translation_key
        return None

    @property
    def is_on(self) -> bool | None:
        """Return state of the switch."""
        return getattr(self._device, self._value_attribute)

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID.

        This is for backward-compatibility, so that existing switch-unique_ids will not change.
        """
        if (
            hasattr(self.entity_description, "translation_key")
            and self.entity_description.translation_key is not None
        ):
            return f"{self._device.device_id}_{self._device.channel_id}_{self.entity_description.key}"

        return f"{self._device.device_id}_{self._device.channel_id}_switch"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await getattr(self._device, f"turn_on_{self._value_attribute}", "turn_on")()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await getattr(self._device, f"turn_off_{self._value_attribute}", "turn_off")()

    async def async_update(self, **kwargs: Any) -> None:
        """Update the switch state."""
        await self._device.refresh_state()
