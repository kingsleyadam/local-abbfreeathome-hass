"""Create ABB-free@home binary sensor entities."""

from typing import Any

from abbfreeathome.devices.blind_sensor import BlindSensor
from abbfreeathome.devices.brightness_sensor import BrightnessSensor
from abbfreeathome.devices.carbon_monoxide_sensor import CarbonMonoxideSensor
from abbfreeathome.devices.movement_detector import MovementDetector
from abbfreeathome.devices.rain_sensor import RainSensor
from abbfreeathome.devices.smoke_detector import SmokeDetector
from abbfreeathome.devices.switch_sensor import SwitchSensor
from abbfreeathome.devices.temperature_sensor import TemperatureSensor
from abbfreeathome.devices.wind_sensor import WindSensor
from abbfreeathome.devices.window_door_sensor import WindowDoorSensor
from abbfreeathome.freeathome import FreeAtHome

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SERIAL, DOMAIN

SENSOR_DESCRIPTIONS = {
    "CarbonMonoxideSensorOnOff": {
        "device_class": CarbonMonoxideSensor,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": BinarySensorDeviceClass.CO,
            "translation_key": "carbon_monoxide_sensor",
        },
    },
    "MovementDetectorMotion": {
        "device_class": MovementDetector,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": BinarySensorDeviceClass.MOTION,
            "translation_key": "movement_detector_motion",
        },
    },
    "SmokeDetectorOnOff": {
        "device_class": SmokeDetector,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": BinarySensorDeviceClass.SMOKE,
            "translation_key": "smoke_detector",
        },
    },
    "SwitchSensorOnOff": {
        "device_class": SwitchSensor,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "translation_key": "switch_sensor",
        },
    },
    "BlindSensorShort": {
        "device_class": BlindSensor,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "translation_key": "blind_sensor_short",
        },
    },
    "BlindSensorLong": {
        "device_class": BlindSensor,
        "value_attribute": "longpress",
        "entity_description_kwargs": {
            "translation_key": "blind_sensor_long",
        },
    },
    "WindowDoorSensorOnOff": {
        "device_class": WindowDoorSensor,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": BinarySensorDeviceClass.WINDOW,
            "translation_key": "window_door",
        },
    },
    "RainSensorOnOff": {
        "device_class": RainSensor,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": BinarySensorDeviceClass.MOISTURE,
            "translation_key": "rain_sensor",
        },
    },
    "BrightnessSensorOnOff": {
        "device_class": BrightnessSensor,
        "value_attribute": "alarm",
        "entity_description_kwargs": {
            "device_class": BinarySensorDeviceClass.LIGHT,
            "translation_key": "brightness_sensor",
        },
    },
    "TemperatureSensorOnOff": {
        "device_class": TemperatureSensor,
        "value_attribute": "alarm",
        "entity_description_kwargs": {
            "device_class": BinarySensorDeviceClass.COLD,
            "translation_key": "temperature_sensor",
        },
    },
    "WindSensorOnOff": {
        "device_class": WindSensor,
        "value_attribute": "alarm",
        "entity_description_kwargs": {
            "device_class": BinarySensorDeviceClass.MOVING,
            "translation_key": "wind_sensor",
        },
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities."""
    free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]

    for key, description in SENSOR_DESCRIPTIONS.items():
        async_add_entities(
            FreeAtHomeBinarySensorEntity(
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


class FreeAtHomeBinarySensorEntity(BinarySensorEntity):
    """Defines a free@home binary sensor entity."""

    _attr_should_poll: bool = False
    _attr_has_entity_name: bool = True

    def __init__(
        self,
        device: BrightnessSensor
        | CarbonMonoxideSensor
        | MovementDetector
        | RainSensor
        | SmokeDetector
        | SwitchSensor
        | TemperatureSensor
        | WindowDoorSensor
        | WindSensor,
        value_attribute: str,
        entity_description_kwargs: dict[str:Any],
        sysap_serial_number: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__()
        self._device = device
        self._value_attribute = value_attribute
        self._sysap_serial_number = sysap_serial_number

        # If the channel name is different from the device name, it's likely
        # a dedicated sensor with it's own naming convention. Use it's channel name instead.
        if (
            device.channel_name != device.device_name
            and "translation_key" in entity_description_kwargs
        ):
            entity_description_kwargs.pop("translation_key")

        self.entity_description = BinarySensorEntityDescription(
            name=device.channel_name,
            translation_placeholders={"channel_id": device.channel_id},
            **entity_description_kwargs,
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._device.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._device.remove_callback(self.async_write_ha_state)

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
    def is_on(self) -> bool | None:
        """Return state of the binary sensor."""
        return getattr(self._device, self._value_attribute)

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._device.device_id}_{self._device.channel_id}_{self.entity_description.key}"
