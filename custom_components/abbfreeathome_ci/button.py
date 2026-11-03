"""Create ABB-free@home button entities."""

from typing import Any

from abbfreeathome.channels.trigger import Trigger
from abbfreeathome.channels.virtual.virtual_trigger import VirtualTrigger

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CREATE_SUBDEVICES, CONF_SERIAL, DOMAIN
from .entity import ChannelGetter, FreeAtHomeEntity, async_setup_platform_entities
from .helpers import AnyDeviceInfo, async_get_sub_device_info

BUTTON_DESCRIPTIONS = {
    "Trigger": {
        "channel_class": Trigger,
        "entity_description_kwargs": {
            "key": "button",
        },
    },
    "VirtualTrigger": {
        "channel_class": VirtualTrigger,
        "entity_description_kwargs": {
            "key": "button",
        },
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up buttons."""

    def build_entities(get_channels: ChannelGetter) -> list[FreeAtHomeButtonEntity]:
        return [
            FreeAtHomeButtonEntity(
                channel,
                entity_description_kwargs=description.get("entity_description_kwargs"),
                sysap_serial_number=entry.data[CONF_SERIAL],
                create_subdevices=entry.data[CONF_CREATE_SUBDEVICES],
            )
            for description in BUTTON_DESCRIPTIONS.values()
            for channel in get_channels(description.get("channel_class"))
        ]

    async_setup_platform_entities(hass, entry, async_add_entities, build_entities)


class FreeAtHomeButtonEntity(FreeAtHomeEntity, ButtonEntity):
    """Defines a free@home button entity."""

    _attr_should_poll: bool = False

    def __init__(
        self,
        channel: Trigger | VirtualTrigger,
        entity_description_kwargs: dict[str, Any],
        sysap_serial_number: str,
        create_subdevices: bool,
    ) -> None:
        """Initialize the button."""
        super().__init__()
        self._channel = channel
        self._sysap_serial_number = sysap_serial_number
        self._create_subdevices = create_subdevices

        self.entity_description = ButtonEntityDescription(
            name=channel.channel_name,
            **entity_description_kwargs,
        )

    @property
    def device_info(self) -> AnyDeviceInfo:
        """Information about this entity/device."""
        if self._create_subdevices and self._channel.device.is_multi_device:
            return async_get_sub_device_info(
                self.hass, self.platform.config_entry.entry_id, self._channel
            )

        return DeviceInfo(identifiers={(DOMAIN, self._channel.device_serial)})

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._channel.device_serial}_{self._channel.channel_id}_button"

    async def async_press(self) -> None:
        """Press the button."""
        await self._channel.press()
