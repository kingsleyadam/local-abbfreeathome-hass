"""Create ABB Free@Home event entities."""

from typing import Any

from abbfreeathome.devices.switch_sensor import SwitchSensor
from abbfreeathome.freeathome import FreeAtHome

from homeassistant.components.event import (
    EventDeviceClass,
    EventEntity,
    EventEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SERIAL, DOMAIN


class FreeAtHomeEventDescription:
    """Class describing FreeAtHome sensor entities."""

    def __init__(
        self,
        device_class: SwitchSensor,
        entity_description_kwargs: dict[str:Any],
    ) -> None:
        """Initialize the FreeAtHomeSensorDescription class."""
        self.device_class: SwitchSensor = device_class
        self.entity_description_kwargs = entity_description_kwargs


EVENT_DESCRIPTIONS: tuple[FreeAtHomeEventDescription, ...] = (
    FreeAtHomeEventDescription(
        device_class=SwitchSensor,
        entity_description_kwargs={
            "device_class": EventDeviceClass.BUTTON,
            "event_types": ["On", "Off"],
            "key": "EventSwitchSensorOnOff",
            "translation_key": "switch_sensor",
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

    for description in EVENT_DESCRIPTIONS:
        async_add_entities(
            FreeAtHomeEventEntity(
                device,
                entity_description_kwargs=description.entity_description_kwargs,
                sysap_serial_number=entry.data[CONF_SERIAL],
            )
            for device in free_at_home.get_device_by_class(
                device_class=description.device_class
            )
        )


class FreeAtHomeEventEntity(EventEntity):
    """Free@Home Event Entity."""

    _attr_has_entity_name: bool = True

    def __init__(
        self,
        device: SwitchSensor,
        entity_description_kwargs: dict[str:Any],
        sysap_serial_number: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__()
        self._device = device
        self._sysap_serial_number = sysap_serial_number

        self.entity_description = EventEntityDescription(
            name=device.channel_name,
            translation_placeholders={"channel_id": device.channel_id},
            **entity_description_kwargs,
        )

        self._attr_unique_id = (
            f"{device.device_id}_{device.channel_id}_{self.entity_description.key}"
        )

    @callback
    def _async_handle_event(self) -> None:
        """Handle the demo button event."""

        # TODO: Make this logic dynamic per Free@Home Device,
        # Lambda function or callback within Free@Home object?
        event_type = "On" if self._device.state else "Off"

        self._trigger_event(event_type)

        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Entity being added to hass."""
        self._device.register_callback(self._async_handle_event)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._device.remove_callback(self._async_handle_event)

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
