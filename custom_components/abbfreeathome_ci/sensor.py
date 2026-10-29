"""Create ABB-free@home sensor entities."""

from typing import Any

from abbfreeathome import FreeAtHome
from abbfreeathome.channels.air_quality_sensor import AirQualitySensor
from abbfreeathome.channels.base import Base
from abbfreeathome.channels.brightness_sensor import BrightnessSensor
from abbfreeathome.channels.heating_cooling_sensor import (
    HeatingCoolingSensor,
    HeatingCoolingSensorState,
)
from abbfreeathome.channels.movement_detector import (
    BlockableMovementDetector,
    MovementDetector,
)
from abbfreeathome.channels.temperature_sensor import TemperatureSensor
from abbfreeathome.channels.wind_sensor import WindSensor
from abbfreeathome.channels.window_door_sensor import (
    WindowDoorSensor,
    WindowDoorSensorPosition,
)
from abbfreeathome.device import Device

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import LIGHT_LUX, PERCENTAGE, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CREATE_SUBDEVICES, CONF_SERIAL, DOMAIN, MANUFACTURER
from .helpers import async_get_via_device_kwargs

try:
    from homeassistant.const import UnitOfRatio
except ImportError:
    # Older supported HA versions do not yet have UnitOfRatio.
    from homeassistant.const import CONCENTRATION_PARTS_PER_MILLION as PARTS_PER_MILLION
else:
    PARTS_PER_MILLION = UnitOfRatio.PARTS_PER_MILLION

SENSOR_DESCRIPTIONS = {
    "AirQualitySensorCO2": {
        "channel_class": AirQualitySensor,
        "value_attribute": "co2",
        "entity_description_kwargs": {
            "device_class": SensorDeviceClass.CO2,
            "native_unit_of_measurement": PARTS_PER_MILLION,
            "state_class": SensorStateClass.MEASUREMENT,
            "translation_key": "air_quality_sensor_co2",
        },
    },
    "AirQualitySensorVOC": {
        "channel_class": AirQualitySensor,
        "value_attribute": "voc_index",
        "entity_description_kwargs": {
            "device_class": SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS_PARTS,
            "state_class": SensorStateClass.MEASUREMENT,
            "translation_key": "air_quality_sensor_voc",
        },
    },
    "AirQualitySensorHumidity": {
        "channel_class": AirQualitySensor,
        "value_attribute": "humidity",
        "entity_description_kwargs": {
            "device_class": SensorDeviceClass.HUMIDITY,
            "native_unit_of_measurement": PERCENTAGE,
            "state_class": SensorStateClass.MEASUREMENT,
            "translation_key": "air_quality_sensor_humidity",
        },
    },
    "BrightnessSensor": {
        "channel_class": BrightnessSensor,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": SensorDeviceClass.ILLUMINANCE,
            "native_unit_of_measurement": LIGHT_LUX,
            "state_class": SensorStateClass.MEASUREMENT,
            "translation_key": "brightness_sensor",
        },
    },
    "HeatingCoolingSensor": {
        "channel_class": HeatingCoolingSensor,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": SensorDeviceClass.ENUM,
            "options": [state.name for state in HeatingCoolingSensorState],
            "translation_key": "heating_cooling_sensor",
        },
    },
    "MovementDetectorBrightness": {
        "channel_class": MovementDetector,
        "value_attribute": "brightness",
        "entity_description_kwargs": {
            "device_class": SensorDeviceClass.ILLUMINANCE,
            "native_unit_of_measurement": LIGHT_LUX,
            "state_class": SensorStateClass.MEASUREMENT,
            "translation_key": "movement_detector_brightness",
        },
    },
    "BlockableMovementDetectorBrightness": {
        "channel_class": BlockableMovementDetector,
        "value_attribute": "brightness",
        "entity_description_kwargs": {
            "device_class": SensorDeviceClass.ILLUMINANCE,
            "native_unit_of_measurement": LIGHT_LUX,
            "state_class": SensorStateClass.MEASUREMENT,
            "translation_key": "movement_detector_brightness",
        },
    },
    "WindowDoorSensorPosition": {
        "channel_class": WindowDoorSensor,
        "value_attribute": "position",
        "entity_description_kwargs": {
            "device_class": SensorDeviceClass.ENUM,
            "options": [position.name for position in WindowDoorSensorPosition],
            "translation_key": "window_position",
        },
    },
    "TemperatureSensor": {
        "channel_class": TemperatureSensor,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": SensorDeviceClass.TEMPERATURE,
            "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
            "state_class": SensorStateClass.MEASUREMENT,
            "translation_key": "temperature_sensor",
        },
    },
    "WindSensorSpeed": {
        "channel_class": WindSensor,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": SensorDeviceClass.WIND_SPEED,
            "native_unit_of_measurement": UnitOfSpeed.METERS_PER_SECOND,
            "state_class": SensorStateClass.MEASUREMENT,
            "translation_key": "wind_sensor_speed",
        },
    },
    "WindSensorForce": {
        "channel_class": WindSensor,
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
                channel,
                value_attribute=description.get("value_attribute"),
                entity_description_kwargs={"key": key}
                | description.get("entity_description_kwargs"),
                sysap_serial_number=entry.data[CONF_SERIAL],
                create_subdevices=entry.data[CONF_CREATE_SUBDEVICES],
            )
            for channel in free_at_home.get_channels_by_class(
                channel_class=description.get("channel_class")
            )
            if getattr(channel, description.get("value_attribute")) is not None
        )

    parameter_entities = []
    for device in free_at_home.get_devices().values():
        channels = free_at_home.get_channels_by_device(device.device_serial)
        if not channels:
            continue
        if entry.data[CONF_CREATE_SUBDEVICES] and device.is_multi_device:
            if device.parameters:
                parameter_entities.append(FreeAtHomeParametersSensor(device, []))
            parameter_entities.extend(
                FreeAtHomeParametersSensor(None, [channel])
                for channel in channels
                if channel.parameters
            )
        elif device.parameters or any(channel.parameters for channel in channels):
            parameter_entities.append(FreeAtHomeParametersSensor(device, channels))
    async_add_entities(parameter_entities)


class FreeAtHomeParametersSensor(SensorEntity):
    """Expose parameters belonging to a physical device or channel sub-device."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "parameters"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:tune"

    def __init__(self, device: Device | None, channels: list[Base]) -> None:
        """Initialize the parameter aggregate."""
        super().__init__()
        self._device = device
        self._channels = channels
        serial = (
            device.device_serial
            if device is not None
            else f"{channels[0].device_serial}_{channels[0].channel_id}"
        )
        self._attr_unique_id = f"{serial}_parameters"

    @property
    def device_info(self) -> DeviceInfo:
        """Attach to the same physical device or sub-device as operational entities."""
        if self._device is not None:
            return DeviceInfo(identifiers={(DOMAIN, self._device.device_serial)})

        channel = self._channels[0]
        serial = f"{channel.device_serial}_{channel.channel_id}"
        return DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=f"{channel.device_name} ({channel.channel_id})",
            manufacturer=MANUFACTURER,
            serial_number=serial,
            hw_version=f"{channel.device.device_id} (sub)",
            suggested_area=channel.room_name,
            **async_get_via_device_kwargs(
                self.hass,
                self.platform.config_entry.entry_id,
                channel.device_serial,
            ),
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to device and included channel parameter changes."""
        if self._device is not None:
            self._device.register_parameter_callback(self.async_write_ha_state)
        for channel in self._channels:
            channel.register_parameter_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from parameter changes."""
        if self._device is not None:
            self._device.remove_parameter_callback(self.async_write_ha_state)
        for channel in self._channels:
            channel.remove_parameter_callback(self.async_write_ha_state)

    @property
    def native_value(self) -> int:
        """Return the number of exposed parameters, not a measurement."""
        device_count = len(self._device.parameters) if self._device is not None else 0
        return device_count + sum(len(channel.parameters) for channel in self._channels)

    @staticmethod
    def _named_parameters(source: Device | Base) -> dict[str, Any]:
        """Snapshot parameter values using names, or IDs for unknown parameters."""
        return {
            source.get_parameter_name(parameter_id) or parameter_id: value
            for parameter_id, value in source.parameters.items()
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return independent snapshots so library updates cannot mutate HA state."""
        attributes = {}
        if self._device is not None and self._device.parameters:
            attributes["device_parameters"] = self._named_parameters(self._device)
        channel_parameters = {
            channel.channel_id: {
                "name": channel.channel_name,
                "parameters": self._named_parameters(channel),
            }
            for channel in self._channels
            if channel.parameters
        }
        if channel_parameters:
            attributes["channel_parameters"] = channel_parameters
        return attributes


class FreeAtHomeSensorEntity(SensorEntity):
    """Defines a free@home sensor entity."""

    _attr_should_poll: bool = False

    def __init__(
        self,
        channel: AirQualitySensor
        | BrightnessSensor
        | HeatingCoolingSensor
        | MovementDetector
        | TemperatureSensor
        | WindSensor,
        value_attribute: str,
        entity_description_kwargs: dict[str, Any],
        sysap_serial_number: str,
        create_subdevices: bool,
    ) -> None:
        """Initialize the sensor."""
        super().__init__()
        self._channel = channel
        self._value_attribute = value_attribute
        self._sysap_serial_number = sysap_serial_number
        self._create_subdevices = create_subdevices

        self.entity_description = SensorEntityDescription(
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
    def native_value(self) -> float | None:
        """Return state of the sensor."""
        return getattr(self._channel, self._value_attribute)

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._channel.device_serial}_{self._channel.channel_id}_{self.entity_description.key}"
