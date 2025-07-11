"""Create ABB-free@home event entities."""

from typing import Any

from abbfreeathome import FreeAtHome
from abbfreeathome.channels.blind_sensor import BlindSensor, BlindSensorState
from abbfreeathome.channels.des_door_ringing_sensor import DesDoorRingingSensor
from abbfreeathome.channels.force_on_off_sensor import (
    ForceOnOffSensor,
    ForceOnOffSensorState,
)
from abbfreeathome.channels.switch_sensor import (
    DimmingSensor,
    DimmingSensorState,
    SwitchSensor,
    SwitchSensorState,
)
from abbfreeathome.channels.virtual.virtual_switch_actuator import VirtualSwitchActuator

from homeassistant.components.event import (
    EventDeviceClass,
    EventEntity,
    EventEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CREATE_SUBDEVICES, CONF_SERIAL, DOMAIN

EVENT_DESCRIPTIONS = {
    "EventBlindSensorState": {
        "channel_class": BlindSensor,
        "event_type_callback": lambda state: state,
        "state_attribute": "state",
        "entity_description_kwargs": {
            "device_class": EventDeviceClass.BUTTON,
            "event_types": [state.name for state in BlindSensorState],
            "translation_key": "blind_sensor",
        },
    },
    "EventDesDoorRingingSensorActivated": {
        "channel_class": DesDoorRingingSensor,
        "event_type_callback": lambda: "activated",
        "state_attribute": "",
        "entity_description_kwargs": {
            "device_class": EventDeviceClass.BUTTON,
            "event_types": ["activated"],
            "translation_key": "des_door_ringing_sensor",
        },
    },
    "EventDimmingSensorState": {
        "channel_class": DimmingSensor,
        "event_type_callback": lambda state: state,
        "state_attribute": "state",
        "entity_description_kwargs": {
            "device_class": EventDeviceClass.BUTTON,
            "event_types": list(
                set(
                    [state.name for state in SwitchSensorState]
                    + [state.name for state in DimmingSensorState]
                )
            ),
            "translation_key": "dimming_sensor",
        },
    },
    "EventForceOnOffSensorOnOff": {
        "channel_class": ForceOnOffSensor,
        "event_type_callback": lambda state: state,
        "state_attribute": "state",
        "entity_description_kwargs": {
            "device_class": EventDeviceClass.BUTTON,
            "event_types": [state.name for state in ForceOnOffSensorState],
            "translation_key": "force_on_off_sensor",
        },
    },
    "EventSwitchSensorOnOff": {
        "channel_class": SwitchSensor,
        "event_type_callback": lambda state: state,
        "state_attribute": "state",
        "entity_description_kwargs": {
            "device_class": EventDeviceClass.BUTTON,
            "event_types": [state.name for state in SwitchSensorState],
            "translation_key": "switch_sensor",
        },
    },
    "EventVirtualSwitchActuatorOnOff": {
        "channel_class": VirtualSwitchActuator,
        "event_type_callback": lambda requested_state: "On"
        if requested_state
        else "Off",
        "state_attribute": "requested_state",
        "entity_description_kwargs": {
            "device_class": EventDeviceClass.BUTTON,
            "event_types": ["On", "Off"],
            "translation_key": "virtual_switch_actuator_onoff",
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
                channel,
                state_attribute=description.get("state_attribute"),
                entity_description_kwargs={"key": key}
                | description.get("entity_description_kwargs"),
                sysap_serial_number=entry.data[CONF_SERIAL],
                create_subdevices=entry.data[CONF_CREATE_SUBDEVICES],
                event_type_callback=description.get("event_type_callback"),
            )
            for channel in free_at_home.get_channels_by_class(
                channel_class=description.get("channel_class")
            )
        )


class FreeAtHomeEventEntity(EventEntity):
    """free@home Event Entity."""

    def __init__(
        self,
        channel: BlindSensor
        | DesDoorRingingSensor
        | DimmingSensor
        | ForceOnOffSensor
        | SwitchSensor
        | VirtualSwitchActuator,
        state_attribute: str,
        entity_description_kwargs: dict[str:Any],
        sysap_serial_number: str,
        create_subdevices: bool,
        event_type_callback: callback,
    ) -> None:
        """Initialize the sensor."""
        super().__init__()
        self._channel = channel
        self._state_attribute = state_attribute
        self._sysap_serial_number = sysap_serial_number
        self._create_subdevices = create_subdevices
        self._event_type_callback = event_type_callback

        self.entity_description = EventEntityDescription(
            has_entity_name=True,
            name=channel.channel_name,
            translation_placeholders={"channel_id": channel.channel_id},
            **entity_description_kwargs,
        )

    @callback
    def _async_handle_event(self) -> None:
        """Handle the demo button event."""

        if hasattr(self._channel, self._state_attribute):
            event_type = self._event_type_callback(
                getattr(self._channel, self._state_attribute)
            )
        else:
            event_type = self._event_type_callback()

        self._trigger_event(event_type)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Entity being added to hass."""
        if len(self._state_attribute) > 0:
            self._channel.register_callback(
                callback_attribute=self._state_attribute,
                callback=self._async_handle_event,
            )
        else:
            self._channel.register_callback(
                callback_attribute="state", callback=self._async_handle_event
            )

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        if len(self._state_attribute) > 0:
            self._channel.remove_callback(
                callback_attribute=self._state_attribute,
                callback=self._async_handle_event,
            )
        else:
            self._channel.remove_callback(
                callback_attribute="state", callback=self._async_handle_event
            )

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        if self._create_subdevices and self._channel.device.is_multi_device:
            return {
                "identifiers": {
                    (
                        DOMAIN,
                        f"{self._channel.device_serial}_{self._channel.channel_id}",
                    )
                },
                "name": self._channel.channel_name,
                "manufacturer": "ABB Busch-Jaeger",
                "serial_number": f"{self._channel.device_serial}_{self._channel.channel_id}",
                "suggested_area": self._channel.room_name,
                "via_device": (DOMAIN, self._channel.device_serial),
            }

        return {
            "identifiers": {(DOMAIN, self._channel.device_serial)},
            "name": self._channel.device_name,
            "manufacturer": "ABB Busch-Jaeger",
            "serial_number": self._channel.device_serial,
            "suggested_area": self._channel.device.room_name,
            "via_device": (DOMAIN, self._sysap_serial_number),
        }

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._channel.device_serial}_{self._channel.channel_id}_{self.entity_description.key}"
