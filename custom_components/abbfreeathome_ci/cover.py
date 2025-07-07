"""Create ABB-free@home cover entities."""

from typing import Any

from abbfreeathome import FreeAtHome
from abbfreeathome.channels.cover_actuator import (
    AtticWindowActuator,
    AwningActuator,
    BlindActuator,
    CoverActuatorState,
    ShutterActuator,
)

from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityDescription,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CREATE_SUBDEVICES, CONF_SERIAL, DOMAIN

SELECT_DESCRIPTIONS = {
    "AtticWindowActuator": {
        "channel_class": AtticWindowActuator,
        "entity_description_kwargs": {
            "device_class": CoverDeviceClass.WINDOW,
        },
    },
    "AwningActuator": {
        "channel_class": AwningActuator,
        "entity_description_kwargs": {
            "device_class": CoverDeviceClass.AWNING,
        },
    },
    "BlindActuator": {
        "channel_class": BlindActuator,
        "entity_description_kwargs": {
            "device_class": CoverDeviceClass.SHUTTER,
        },
    },
    "ShutterActuator": {
        "channel_class": ShutterActuator,
        "entity_description_kwargs": {
            "device_class": CoverDeviceClass.BLIND,
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
            FreeAtHomeCoverEntity(
                channel,
                entity_description_kwargs={"key": key}
                | description.get("entity_description_kwargs"),
                sysap_serial_number=entry.data[CONF_SERIAL],
                hass=hass,
                create_subdevices=entry.data[CONF_CREATE_SUBDEVICES],
                config_entry_id=entry.entry_id,
            )
            for channel in free_at_home.get_channels_by_class(
                channel_class=description.get("channel_class")
            )
        )


class FreeAtHomeCoverEntity(CoverEntity):
    """Defines a free@home cover entity."""

    _attr_should_poll: bool = False
    _callback_attributes: list[str] = [
        "state",
        "position",
    ]

    def __init__(
        self,
        channel: AtticWindowActuator | AwningActuator | BlindActuator | ShutterActuator,
        entity_description_kwargs: dict[str:Any],
        sysap_serial_number: str,
        hass: HomeAssistant,
        create_subdevices: bool,
        config_entry_id: str,
    ) -> None:
        """Initialize the cover."""
        super().__init__()
        self._channel = channel
        self._sysap_serial_number = sysap_serial_number
        self._create_subdevices = create_subdevices

        self.entity_description = CoverEntityDescription(
            has_entity_name=True,
            name=channel.channel_name,
            **entity_description_kwargs,
        )

        if self._create_subdevices and self._channel.device.floor is None:
            device_registry = dr.async_get(hass)
            device_registry.async_get_or_create(
                config_entry_id=config_entry_id,
                identifiers={(DOMAIN, self._channel.device_serial)},
                name=self._channel.device_name,
                manufacturer="ABB Busch-Jaeger",
                serial_number=self._channel.device_serial,
                suggested_area=None,
                via_device=(DOMAIN, self._sysap_serial_number),
            )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        for _callback_attribute in self._callback_attributes:
            self._channel.register_callback(
                callback_attribute=_callback_attribute,
                callback=self.async_write_ha_state,
            )

        if hasattr(self._channel, "tilt_position"):
            self._channel.register_callback(
                callback_attribute="tilt_position", callback=self.async_write_ha_state
            )

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        for _callback_attribute in self._callback_attributes:
            self._channel.remove_callback(
                callback_attribute=_callback_attribute,
                callback=self.async_write_ha_state,
            )

        if hasattr(self._channel, "tilt_position"):
            self._channel.remove_callback(
                callback_attribute="tilt_position", callback=self.async_write_ha_state
            )

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        if self._create_subdevices and self._channel.device.floor is None:
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
    def current_cover_position(self) -> int:
        """Get current position."""
        return abs(self._channel.position - 100)

    @property
    def current_cover_tilt_position(self) -> int | None:
        """Get current tilt position."""

        if hasattr(self._channel, "tilt_position"):
            return abs(self._channel.tilt_position - 100)
        return None

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._channel.device_serial}_{self._channel.channel_id}_{self.entity_description.key}"

    @property
    def is_closed(self) -> bool:
        """If the cover is closed or not."""
        return self._channel.position == 100

    @property
    def is_closing(self) -> bool:
        """If the cover is closing or not."""
        return self._channel.state == CoverActuatorState.closing.name

    @property
    def is_opening(self) -> bool:
        """If the cover is opening or not."""
        return self._channel.state == CoverActuatorState.opening.name

    @property
    def supported_features(self) -> CoverEntityFeature:
        """Return the list of supported features."""

        _features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.SET_POSITION
            | CoverEntityFeature.STOP
        )

        if hasattr(self._channel, "tilt_position"):
            _features |= CoverEntityFeature.SET_TILT_POSITION

        return _features

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        await self._channel.open()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close cover."""
        await self._channel.close()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""

        _position = abs(kwargs[ATTR_POSITION] - 100)
        await self._channel.set_position(_position)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        await self._channel.stop()

    async def async_set_cover_tilt_position(self, **kwargs: Any) -> None:
        """Move the cover tilt to a specific position."""
        _tilt_position = abs(kwargs[ATTR_TILT_POSITION] - 100)
        await self._channel.set_tilt_position(_tilt_position)
