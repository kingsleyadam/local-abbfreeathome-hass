"""Create ABB Free@Home binary sensor entities."""

from typing import Any

from abbfreeathome.devices.movement_detector import MovementDetector
from abbfreeathome.devices.switch_sensor import SwitchSensor
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


class FreeAtHomeBinarySensorDescription:
    """Class describing FreeAtHome sensor entities."""

    def __init__(
        self,
        device_class: MovementDetector | SwitchSensor | WindowDoorSensor,
        value_attribute: str,
        entity_description_kwargs: dict[str:Any],
    ) -> None:
        """Initialize the FreeAtHomeSensorDescription class."""
        self.device_class: MovementDetector | SwitchSensor | WindowDoorSensor = (
            device_class
        )
        self.value_attribute: str = value_attribute
        self.entity_description_kwargs = entity_description_kwargs


SENSOR_DESCRIPTIONS: tuple[FreeAtHomeBinarySensorDescription, ...] = (
    FreeAtHomeBinarySensorDescription(
        device_class=MovementDetector,
        value_attribute="state",
        entity_description_kwargs={
            "device_class": BinarySensorDeviceClass.MOTION,
            "key": "MovementDetectorMotion",
            "translation_key": "movement_detector_motion",
        },
    ),
    FreeAtHomeBinarySensorDescription(
        device_class=SwitchSensor,
        value_attribute="state",
        entity_description_kwargs={
            "key": "SwitchSensorOnOff",
            "translation_key": "switch_sensor",
        },
    ),
    FreeAtHomeBinarySensorDescription(
        device_class=WindowDoorSensor,
        value_attribute="state",
        entity_description_kwargs={
            "device_class": BinarySensorDeviceClass.WINDOW,
            "key": "WindowDoorSensorOnOff",
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities."""
    free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]

    for description in SENSOR_DESCRIPTIONS:
        async_add_entities(
            FreeAtHomeBinarySensorEntity(
                device,
                value_attribute=description.value_attribute,
                entity_description_kwargs=description.entity_description_kwargs,
                sysap_serial_number=entry.data[CONF_SERIAL],
            )
            for device in free_at_home.get_device_by_class(
                device_class=description.device_class
            )
            if getattr(device, description.value_attribute) is not None
        )


class FreeAtHomeBinarySensorEntity(BinarySensorEntity):
    """Defines a Free@Home binary sensor entity."""

    _attr_should_poll: bool = False
    _attr_has_entity_name: bool = True

    def __init__(
        self,
        device: MovementDetector | SwitchSensor | WindowDoorSensor,
        value_attribute: str,
        entity_description_kwargs: dict[str:Any],
        sysap_serial_number: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__()
        self._device = device
        self._value_attribute = value_attribute
        self._sysap_serial_number = sysap_serial_number

        self.entity_description = BinarySensorEntityDescription(
            name=device.channel_name,
            translation_placeholders={"channel_id": device.channel_id},
            **entity_description_kwargs,
        )

        self._attr_unique_id = (
            f"{device.device_id}_{device.channel_id}_{self.entity_description.key}"
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
