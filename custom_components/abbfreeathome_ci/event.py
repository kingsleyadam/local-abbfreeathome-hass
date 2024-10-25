"""Create ABB Free@Home event entities."""

from typing import Any

from abbfreeathome.devices.des_door_ringing_sensor import DesDoorRingingSensor
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

EVENT_DESCRIPTIONS = {
    "EventSwitchSensorOnOff": {
        "device_class": SwitchSensor,
        "event_type_callback": lambda state: "on" if state else "off",
        "entity_description_kwargs": {
            "device_class": EventDeviceClass.BUTTON,
            "event_types": ["on", "off"],
            "translation_key": "switch_sensor",
        },
    },
    "DesDoorRingingSensorActivated": {
        "device_class": DesDoorRingingSensor,
        "event_type_callback": lambda: "activated",
        "entity_description_kwargs": {
            "device_class": EventDeviceClass.BUTTON,
            "event_types": ["activated"],
            "translation_key": "des_door_ringing_sensor",
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

    for key, description in EVENT_DESCRIPTIONS.items():
        async_add_entities(
            FreeAtHomeEventEntity(
                device,
                entity_description_kwargs={"key": key}
                | description.get("entity_description_kwargs"),
                sysap_serial_number=entry.data[CONF_SERIAL],
                event_type_callback=description.get("event_type_callback"),
            )
            for device in free_at_home.get_devices_by_class(
                device_class=description.get("device_class")
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
        event_type_callback: callback,
    ) -> None:
        """Initialize the sensor."""
        super().__init__()
        self._device = device
        self._sysap_serial_number = sysap_serial_number
        self._event_type_callback = event_type_callback

        self.entity_description = EventEntityDescription(
            name=device.channel_name,
            translation_placeholders={"channel_id": device.channel_id},
            **entity_description_kwargs,
        )

    @callback
    def _async_handle_event(self) -> None:
        """Handle the demo button event."""

        if hasattr(self._device, "state"):
            event_type = self._event_type_callback(self._device.state)
        else:
            event_type = self._event_type_callback()

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

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._device.device_id}_{self._device.channel_id}_{self.entity_description.key}"
