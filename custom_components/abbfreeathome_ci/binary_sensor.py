"""Create ABB-free@home binary sensor entities."""

from typing import Any

from abbfreeathome import FreeAtHome
from abbfreeathome.channels.brightness_sensor import BrightnessSensor
from abbfreeathome.channels.carbon_monoxide_sensor import CarbonMonoxideSensor
from abbfreeathome.channels.movement_detector import MovementDetector
from abbfreeathome.channels.rain_sensor import RainSensor
from abbfreeathome.channels.smoke_detector import SmokeDetector
from abbfreeathome.channels.temperature_sensor import TemperatureSensor
from abbfreeathome.channels.wind_sensor import WindSensor
from abbfreeathome.channels.window_door_sensor import WindowDoorSensor

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
        "channel_class": CarbonMonoxideSensor,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": BinarySensorDeviceClass.CO,
            "translation_key": "carbon_monoxide_sensor",
        },
    },
    "MovementDetectorMotion": {
        "channel_class": MovementDetector,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": BinarySensorDeviceClass.MOTION,
            "translation_key": "movement_detector_motion",
        },
    },
    "SmokeDetectorOnOff": {
        "channel_class": SmokeDetector,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": BinarySensorDeviceClass.SMOKE,
            "translation_key": "smoke_detector",
        },
    },
    "WindowDoorSensorOnOff": {
        "channel_class": WindowDoorSensor,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": BinarySensorDeviceClass.WINDOW,
            "translation_key": "window_door",
        },
    },
    "RainSensorOnOff": {
        "channel_class": RainSensor,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": BinarySensorDeviceClass.MOISTURE,
            "translation_key": "rain_sensor",
        },
    },
    "BrightnessSensorOnOff": {
        "channel_class": BrightnessSensor,
        "value_attribute": "alarm",
        "entity_description_kwargs": {
            "device_class": BinarySensorDeviceClass.LIGHT,
            "translation_key": "brightness_sensor",
        },
    },
    "TemperatureSensorOnOff": {
        "channel_class": TemperatureSensor,
        "value_attribute": "alarm",
        "entity_description_kwargs": {
            "device_class": BinarySensorDeviceClass.COLD,
            "translation_key": "temperature_sensor",
        },
    },
    "WindSensorOnOff": {
        "channel_class": WindSensor,
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
                channel,
                value_attribute=description.get("value_attribute"),
                entity_description_kwargs={"key": key}
                | description.get("entity_description_kwargs"),
                sysap_serial_number=entry.data[CONF_SERIAL],
            )
            for channel in free_at_home.get_channels_by_class(
                channel_class=description.get("channel_class")
            )
            if getattr(channel, description.get("value_attribute")) is not None
        )


class FreeAtHomeBinarySensorEntity(BinarySensorEntity):
    """Defines a free@home binary sensor entity."""

    _attr_should_poll: bool = False

    def __init__(
        self,
        channel: BrightnessSensor
        | CarbonMonoxideSensor
        | MovementDetector
        | RainSensor
        | SmokeDetector
        | TemperatureSensor
        | WindowDoorSensor
        | WindSensor,
        value_attribute: str,
        entity_description_kwargs: dict[str:Any],
        sysap_serial_number: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__()
        self._channel = channel
        self._value_attribute = value_attribute
        self._sysap_serial_number = sysap_serial_number

        self.entity_description = BinarySensorEntityDescription(
            has_entity_name=True,
            name=channel.channel_name,
            translation_placeholders={"channel_id": channel.channel_id},
            **entity_description_kwargs,
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._channel.register_callback(
            callback_attribute=self._value_attribute, callback=self.async_write_ha_state
        )

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._channel.remove_callback(
            callback_attribute=self._value_attribute, callback=self.async_write_ha_state
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._channel.device_serial)},
            "name": self._channel.device_name,
            "manufacturer": "ABB busch-jaeger",
            "serial_number": self._channel.device_serial,
            "suggested_area": self._channel.room_name,
            "via_device": (DOMAIN, self._sysap_serial_number),
        }

    @property
    def is_on(self) -> bool | None:
        """Return state of the binary sensor."""
        return getattr(self._channel, self._value_attribute)

    @property
    def translation_key(self):
        """Return the translation key to translate the entity's name and states.

        If the device_name and channel_name are the same, then this sensor is not the
        main feature of the device and should have it's name translated.
        """
        _translation_key = None
        if hasattr(self, "_attr_translation_key"):
            _translation_key = self._attr_translation_key
        if hasattr(self, "entity_description"):
            _translation_key = self.entity_description.translation_key

        if self._channel.channel_name == self._channel.device_name:
            return _translation_key
        return None

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._channel.device_serial}_{self._channel.channel_id}_{self.entity_description.key}"
