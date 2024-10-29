"""Create ABB Free@Home sensor entities."""

from typing import Any

from abbfreeathome.devices.brightness_sensor import BrightnessSensor
from abbfreeathome.devices.movement_detector import MovementDetector
from abbfreeathome.devices.temperature_sensor import TemperatureSensor
from abbfreeathome.devices.wind_sensor import WindSensor
from abbfreeathome.devices.window_door_sensor import (
    WindowDoorSensor,
    WindowDoorSensorPosition,
)
from abbfreeathome.freeathome import FreeAtHome

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import LIGHT_LUX, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SERIAL, DOMAIN

SENSOR_DESCRIPTIONS = {
    "BrightnessSensor": {
        "device_class": BrightnessSensor,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": SensorDeviceClass.ILLUMINANCE,
            "native_unit_of_measurement": LIGHT_LUX,
            "state_class": SensorStateClass.MEASUREMENT,
            "translation_key": "brightness_sensor",
        },
    },
    "MovementDetectorBrightness": {
        "device_class": MovementDetector,
        "value_attribute": "brightness",
        "entity_description_kwargs": {
            "device_class": SensorDeviceClass.ILLUMINANCE,
            "native_unit_of_measurement": LIGHT_LUX,
            "state_class": SensorStateClass.MEASUREMENT,
            "translation_key": "movement_detector_brightness",
        },
    },
    "WindowDoorSensorPosition": {
        "device_class": WindowDoorSensor,
        "value_attribute": "position",
        "entity_description_kwargs": {
            "device_class": SensorDeviceClass.ENUM,
            "options": [position.name for position in WindowDoorSensorPosition],
            "translation_key": "window_position",
        },
    },
    "TemperatureSensor": {
        "device_class": TemperatureSensor,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": SensorDeviceClass.TEMPERATURE,
            "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
            "state_class": SensorStateClass.MEASUREMENT,
            "translation_key": "temperature_sensor",
        },
    },
    "WindSensorSpeed": {
        "device_class": WindSensor,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": SensorDeviceClass.WIND_SPEED,
            "native_unit_of_measurement": UnitOfSpeed.METERS_PER_SECOND,
            "state_class": SensorStateClass.MEASUREMENT,
            "translation_key": "wind_sensor_speed",
        },
    },
    "WindSensorForce": {
        "device_class": WindSensor,
        "value_attribute": "force",
        "entity_description_kwargs": {
            "device_class": SensorDeviceClass.WIND_SPEED,
            "native_unit_of_measurement": UnitOfSpeed.BEAUFORT,
            "suggested_unit_of_measurement": UnitOfSpeed.BEAUFORT,
            "state_class": SensorStateClass.MEASUREMENT,
            "translation_key": "wind_sensor_force",
        },
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]

    for key, description in SENSOR_DESCRIPTIONS.items():
        async_add_entities(
            FreeAtHomeSensorEntity(
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


class FreeAtHomeSensorEntity(SensorEntity):
    """Defines a Free@Home sensor entity."""

    _attr_should_poll: bool = False
    _attr_has_entity_name: bool = True

    def __init__(
        self,
        device: BrightnessSensor | MovementDetector | TemperatureSensor | WindSensor,
        value_attribute: str,
        entity_description_kwargs: dict[str:Any],
        sysap_serial_number: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__()
        self._device = device
        self._value_attribute = value_attribute
        self._sysap_serial_number = sysap_serial_number

        self.entity_description = SensorEntityDescription(
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
    def native_value(self) -> float | None:
        """Return state of the sensor."""
        return getattr(self._device, self._value_attribute)

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._device.device_id}_{self._device.channel_id}_{self.entity_description.key}"
