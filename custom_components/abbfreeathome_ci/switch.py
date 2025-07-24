"""Create ABB-free@home switch entities."""

from typing import Any

from abbfreeathome import FreeAtHome
from abbfreeathome.channels.movement_detector import BlockableMovementDetector
from abbfreeathome.channels.switch_actuator import SwitchActuator
from abbfreeathome.channels.switch_sensor import DimmingSensor, SwitchSensor
from abbfreeathome.channels.virtual.virtual_brightness_sensor import (
    VirtualBrightnessSensor,
)
from abbfreeathome.channels.virtual.virtual_rain_sensor import VirtualRainSensor
from abbfreeathome.channels.virtual.virtual_switch_actuator import VirtualSwitchActuator
from abbfreeathome.channels.virtual.virtual_temperature_sensor import (
    VirtualTemperatureSensor,
)
from abbfreeathome.channels.virtual.virtual_wind_sensor import VirtualWindSensor
from abbfreeathome.channels.virtual.virtual_window_door_sensor import (
    VirtualWindowDoorSensor,
)

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CREATE_SUBDEVICES, CONF_SERIAL, DOMAIN, MANUFACTURER

SWITCH_DESCRIPTIONS = {
    "DimmingSensorLed": {
        "channel_class": DimmingSensor,
        "value_attribute": "led",
        "entity_description_kwargs": {
            "device_class": SwitchDeviceClass.SWITCH,
            "translation_key": "sensor_led",
        },
    },
    "SwitchActuator": {
        "channel_class": SwitchActuator,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": SwitchDeviceClass.SWITCH,
        },
    },
    "SwitchSensorLed": {
        "channel_class": SwitchSensor,
        "value_attribute": "led",
        "entity_description_kwargs": {
            "device_class": SwitchDeviceClass.SWITCH,
            "translation_key": "sensor_led",
        },
    },
    "VirtualBrightessSensorAlarm": {
        "channel_class": VirtualBrightnessSensor,
        "value_attribute": "alarm",
        "entity_description_kwargs": {
            "device_class": SwitchDeviceClass.SWITCH,
            "translation_key": "virtual_brightness_sensor",
        },
    },
    "VirtualRainSensorAlarm": {
        "channel_class": VirtualRainSensor,
        "value_attribute": "alarm",
        "entity_description_kwargs": {
            "device_class": SwitchDeviceClass.SWITCH,
            "translation_key": "virtual_rain_sensor",
        },
    },
    "VirtualSwitchActuatorOnOff": {
        "channel_class": VirtualSwitchActuator,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": SwitchDeviceClass.SWITCH,
        },
    },
    "VirtualWindSensorAlarm": {
        "channel_class": VirtualWindSensor,
        "value_attribute": "alarm",
        "entity_description_kwargs": {
            "device_class": SwitchDeviceClass.SWITCH,
            "translation_key": "virtual_wind_sensor",
        },
    },
    "VirtualWindowDoorSensorOnOff": {
        "channel_class": VirtualWindowDoorSensor,
        "value_attribute": "state",
        "entity_description_kwargs": {
            "device_class": SwitchDeviceClass.SWITCH,
        },
    },
    "VirtualTemperatureSensorAlarm": {
        "channel_class": VirtualTemperatureSensor,
        "value_attribute": "alarm",
        "entity_description_kwargs": {
            "device_class": SwitchDeviceClass.SWITCH,
            "translation_key": "virtual_temperature_sensor",
        },
    },
    "BlockableMovementDetector": {
        "channel_class": BlockableMovementDetector,
        "value_attribute": "blocked",
        "entity_description_kwargs": {
            "device_class": SwitchDeviceClass.SWITCH,
            "translation_key": "movement_detector_block",
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


class FreeAtHomeSwitchEntity(SwitchEntity):
    """Defines a free@home switch entity."""

    _attr_should_poll: bool = False

    def __init__(
        self,
        channel: DimmingSensor
        | SwitchActuator
        | SwitchSensor
        | VirtualBrightnessSensor
        | VirtualSwitchActuator
        | VirtualWindowDoorSensor,
        value_attribute: str,
        entity_description_kwargs: dict[str:Any],
        sysap_serial_number: str,
        create_subdevices: bool,
    ) -> None:
        """Initialize the sensor."""
        super().__init__()
        self._channel = channel
        self._value_attribute = value_attribute
        self._sysap_serial_number = sysap_serial_number
        self._create_subdevices = create_subdevices

        self.entity_description = SwitchEntityDescription(
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
                via_device=(DOMAIN, self._channel.device_serial),
            )

        return DeviceInfo(identifiers={(DOMAIN, self._channel.device_serial)})

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

        if self._channel.channel_name == self._channel.device_name:
            return _translation_key
        return None

    @property
    def is_on(self) -> bool | None:
        """Return state of the switch."""
        return getattr(self._channel, self._value_attribute)

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID.

        This is for backward-compatibility, so that existing switch-unique_ids will not change.
        """
        if (
            hasattr(self.entity_description, "translation_key")
            and self.entity_description.translation_key is not None
        ):
            return f"{self._channel.device_serial}_{self._channel.channel_id}_{self.entity_description.key}"

        return f"{self._channel.device_serial}_{self._channel.channel_id}_switch"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        _method = getattr(self._channel, f"turn_on_{self._value_attribute}", None)

        if callable(_method):
            await _method()
        else:
            await self._channel.turn_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        _method = getattr(self._channel, f"turn_off_{self._value_attribute}", None)

        if callable(_method):
            await _method()
        else:
            await self._channel.turn_off()

    async def async_update(self, **kwargs: Any) -> None:
        """Update the switch state."""
        await self._channel.refresh_state()
