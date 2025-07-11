"""Create ABB-free@home switch entities."""

from typing import Any

from abbfreeathome import FreeAtHome
from abbfreeathome.channels.cover_actuator import (
    AtticWindowActuator,
    AwningActuator,
    BlindActuator,
    CoverActuatorForcedPosition,
    ShutterActuator,
)
from abbfreeathome.channels.dimming_actuator import (
    DimmingActuator,
    DimmingActuatorForcedPosition,
)
from abbfreeathome.channels.switch_actuator import (
    SwitchActuator,
    SwitchActuatorForcedPosition,
)

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CREATE_SUBDEVICES, CONF_SERIAL, DOMAIN

SELECT_DESCRIPTIONS = {
    "AtticWindowActuatorForcedPosition": {
        "channel_class": AtticWindowActuator,
        "current_option_attribute": "forced_position",
        "select_option_method": "set_forced_position",
        "entity_description_kwargs": {
            "options": [
                state.name
                for state in CoverActuatorForcedPosition
                if state.value is not None
            ],
            "translation_key": "cover_actuator",
        },
    },
    "AwningActuatorForcedPosition": {
        "channel_class": AwningActuator,
        "current_option_attribute": "forced_position",
        "select_option_method": "set_forced_position",
        "entity_description_kwargs": {
            "options": [
                state.name
                for state in CoverActuatorForcedPosition
                if state.value is not None
            ],
            "translation_key": "cover_actuator",
        },
    },
    "BlindActuatorForcedPosition": {
        "channel_class": BlindActuator,
        "current_option_attribute": "forced_position",
        "select_option_method": "set_forced_position",
        "entity_description_kwargs": {
            "options": [
                state.name
                for state in CoverActuatorForcedPosition
                if state.value is not None
            ],
            "translation_key": "cover_actuator",
        },
    },
    "ShutterActuatorForcedPosition": {
        "channel_class": ShutterActuator,
        "current_option_attribute": "forced_position",
        "select_option_method": "set_forced_position",
        "entity_description_kwargs": {
            "options": [
                state.name
                for state in CoverActuatorForcedPosition
                if state.value is not None
            ],
            "translation_key": "cover_actuator",
        },
    },
    "SwitchActuatorForcedPosition": {
        "channel_class": SwitchActuator,
        "current_option_attribute": "forced_position",
        "select_option_method": "set_forced_position",
        "entity_description_kwargs": {
            "options": [
                state.name
                for state in SwitchActuatorForcedPosition
                if state.value is not None
            ],
            "translation_key": "switch_actuator",
        },
    },
    "DimmingActuatorForcedPosition": {
        "channel_class": DimmingActuator,
        "current_option_attribute": "forced_position",
        "select_option_method": "set_forced_position",
        "entity_description_kwargs": {
            "options": [
                state.name
                for state in DimmingActuatorForcedPosition
                if state.value is not None
            ],
            "translation_key": "dimming_actuator",
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

    for key, description in SELECT_DESCRIPTIONS.items():
        async_add_entities(
            FreeAtHomeSelectEntity(
                channel,
                entity_description_kwargs={"key": key}
                | description.get("entity_description_kwargs"),
                current_option_attribute=description.get("current_option_attribute"),
                select_option_method=description.get("select_option_method"),
                sysap_serial_number=entry.data[CONF_SERIAL],
                create_subdevices=entry.data[CONF_CREATE_SUBDEVICES],
            )
            for channel in free_at_home.get_channels_by_class(
                channel_class=description.get("channel_class")
            )
        )


class FreeAtHomeSelectEntity(SelectEntity):
    """Defines a free@home switch entity."""

    _attr_should_poll: bool = False

    def __init__(
        self,
        channel: AtticWindowActuator
        | AwningActuator
        | BlindActuator
        | DimmingActuator
        | ShutterActuator
        | SwitchActuator,
        entity_description_kwargs: dict[str:Any],
        current_option_attribute: str,
        select_option_method: str,
        sysap_serial_number: str,
        create_subdevices: bool,
    ) -> None:
        """Initialize the switch."""
        super().__init__()
        self._channel = channel
        self._current_option_attribute = current_option_attribute
        self._select_option_method = select_option_method
        self._sysap_serial_number = sysap_serial_number
        self._create_subdevices = create_subdevices

        self.entity_description = SelectEntityDescription(
            has_entity_name=True,
            name=channel.channel_name,
            translation_placeholders={
                "channel_id": channel.channel_id,
                "channel_name": channel.channel_name,
            },
            **entity_description_kwargs,
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._channel.register_callback(
            callback_attribute=self._current_option_attribute,
            callback=self.async_write_ha_state,
        )

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._channel.remove_callback(
            callback_attribute=self._current_option_attribute,
            callback=self.async_write_ha_state,
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
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        return getattr(self._channel, self._current_option_attribute)

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._channel.device_serial}_{self._channel.channel_id}_{self.entity_description.key}"

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await getattr(self._channel, self._select_option_method)(option)
