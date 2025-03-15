"""Create ABB-free@home switch entities."""

from typing import Any

from abbfreeathome.devices.cover_actuator import (
    AtticWindowActuator,
    AwningActuator,
    BlindActuator,
    CoverActuatorForcedPosition,
    ShutterActuator,
)
from abbfreeathome.devices.dimming_actuator import (
    DimmingActuator,
    DimmingActuatorForcedPosition,
)
from abbfreeathome.devices.switch_actuator import (
    SwitchActuator,
    SwitchActuatorForcedPosition,
)
from abbfreeathome.freeathome import FreeAtHome

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SERIAL, DOMAIN

SELECT_DESCRIPTIONS = {
    "AtticWindowActuatorForcedPosition": {
        "device_class": AtticWindowActuator,
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
        "device_class": AwningActuator,
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
        "device_class": BlindActuator,
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
        "device_class": ShutterActuator,
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
        "device_class": SwitchActuator,
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
        "device_class": DimmingActuator,
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
                device,
                entity_description_kwargs={"key": key}
                | description.get("entity_description_kwargs"),
                current_option_attribute=description.get("current_option_attribute"),
                select_option_method=description.get("select_option_method"),
                sysap_serial_number=entry.data[CONF_SERIAL],
            )
            for device in free_at_home.get_devices_by_class(
                device_class=description.get("device_class")
            )
        )


class FreeAtHomeSelectEntity(SelectEntity):
    """Defines a free@home switch entity."""

    _attr_should_poll: bool = False

    def __init__(
        self,
        device: AtticWindowActuator
        | AwningActuator
        | BlindActuator
        | DimmingActuator
        | ShutterActuator
        | SwitchActuator,
        entity_description_kwargs: dict[str:Any],
        current_option_attribute: str,
        select_option_method: str,
        sysap_serial_number: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__()
        self._device = device
        self._current_option_attribute = current_option_attribute
        self._select_option_method = select_option_method
        self._sysap_serial_number = sysap_serial_number

        self.entity_description = SelectEntityDescription(
            has_entity_name=True,
            name=device.channel_name,
            translation_placeholders={
                "channel_id": device.channel_id,
                "channel_name": device.channel_name,
            },
            **entity_description_kwargs,
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._device.register_callback(
            callback_attribute=self._current_option_attribute,
            callback=self.async_write_ha_state,
        )

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._device.remove_callback(
            callback_attribute=self._current_option_attribute,
            callback=self.async_write_ha_state,
        )

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
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        return getattr(self._device, self._current_option_attribute)

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._device.device_id}_{self._device.channel_id}_{self.entity_description.key}"

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await getattr(self._device, self._select_option_method)(option)
