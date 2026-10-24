"""Create ABB-free@home binary sensor entities."""

from typing import Any

from abbfreeathome import FreeAtHome
from abbfreeathome.channels.air_quality_sensor import AirQualitySensor
from abbfreeathome.channels.brightness_sensor import BrightnessSensor
from abbfreeathome.channels.carbon_monoxide_sensor import CarbonMonoxideSensor
from abbfreeathome.channels.movement_detector import (
    BlockableMovementDetector,
    MovementDetector,
)
from abbfreeathome.channels.rain_sensor import RainSensor
from abbfreeathome.channels.smoke_detector import SmokeDetector
from abbfreeathome.channels.temperature_sensor import TemperatureSensor
from abbfreeathome.channels.wind_sensor import WindSensor
from abbfreeathome.channels.window_door_sensor import WindowDoorSensor
from abbfreeathome.device import Device

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CREATE_SUBDEVICES, CONF_SERIAL, DOMAIN, MANUFACTURER
from .coordinator import FreeAtHomeDeviceStatusCoordinator
from .helpers import async_get_via_device_kwargs

SENSOR_DESCRIPTIONS = {
    "AirQualitySensorCO2Alert": {
        "channel_class": AirQualitySensor,
        "value_attribute": "co2_alert",
        "entity_description_kwargs": {
            "device_class": BinarySensorDeviceClass.GAS,
            "translation_key": "air_quality_sensor_co2_alert",
        },
    },
    "AirQualitySensorVOCAlert": {
        "channel_class": AirQualitySensor,
        "value_attribute": "voc_alert",
        "entity_description_kwargs": {
            "device_class": BinarySensorDeviceClass.GAS,
            "translation_key": "air_quality_sensor_voc_alert",
        },
    },
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
    "BlockableMovementDetectorMotion": {
        "channel_class": BlockableMovementDetector,
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
                create_subdevices=entry.data[CONF_CREATE_SUBDEVICES],
            )
            for channel in free_at_home.get_channels_by_class(
                channel_class=description.get("channel_class")
            )
            if getattr(channel, description.get("value_attribute")) is not None
        )

    # One connectivity sensor per device. A device that stops answering, for
    # example because its battery is empty, is reported by the SysAP as
    # unresponsive. free@home does not expose a battery level over this api.
    _device_status_coordinator: FreeAtHomeDeviceStatusCoordinator = entry.runtime_data

    async_add_entities(
        FreeAtHomeDeviceConnectivityEntity(_device_status_coordinator, device)
        for device in free_at_home.get_devices().values()
        if free_at_home.get_channels_by_device(device.device_serial)
    )


class FreeAtHomeBinarySensorEntity(BinarySensorEntity):
    """Defines a free@home binary sensor entity."""

    _attr_should_poll: bool = False

    def __init__(
        self,
        channel: AirQualitySensor
        | BrightnessSensor
        | CarbonMonoxideSensor
        | MovementDetector
        | RainSensor
        | SmokeDetector
        | TemperatureSensor
        | WindowDoorSensor
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

        return _translation_key

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._channel.device_serial}_{self._channel.channel_id}_{self.entity_description.key}"


class FreeAtHomeDeviceConnectivityEntity(
    CoordinatorEntity[FreeAtHomeDeviceStatusCoordinator], BinarySensorEntity
):
    """Defines a free@home device connectivity entity.

    This is the closest the local api gets to a battery warning: a device that
    stops answering the SysAP is flagged as unresponsive.
    """

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_translation_key = "device_connectivity"

    def __init__(
        self,
        coordinator: FreeAtHomeDeviceStatusCoordinator,
        device: Device,
    ) -> None:
        """Initialize the device connectivity sensor."""
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{device.device_serial}_connectivity"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.device_serial)}
        )

    @property
    def _status(self) -> dict[str, Any] | None:
        """Return the status flags of this device, if the api reported any."""
        return (self.coordinator.data or {}).get(self._device.device_serial)

    @property
    def available(self) -> bool:
        """Return whether the api still reports this device."""
        return super().available and self._status is not None

    @property
    def is_on(self) -> bool | None:
        """Return whether the device is answering the SysAP."""
        if (_status := self._status) is None:
            return None
        return not _status["unresponsive"]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the remaining status flags of the device."""
        if (_status := self._status) is None:
            return None
        return {
            "unresponsive_counter": _status["unresponsive_counter"],
            "defect": _status["defect"],
        }
