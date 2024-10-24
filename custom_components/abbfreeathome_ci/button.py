"""Create ABB Free@Home button entities."""

from abbfreeathome.devices.trigger import Trigger
from abbfreeathome.freeathome import FreeAtHome

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SERIAL, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up buttons."""
    free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        FreeAtHomeButtonEntity(trigger, sysap_serial_number=entry.data[CONF_SERIAL])
        for trigger in free_at_home.get_device_by_class(device_class=Trigger)
    )


class FreeAtHomeButtonEntity(ButtonEntity):
    """Defines a Free@Home button entity."""

    _attr_should_poll: bool = False

    def __init__(self, device: Trigger, sysap_serial_number: str) -> None:
        """Initialize the button."""
        super().__init__()
        self._device = device
        self._sysap_serial_number = sysap_serial_number

        self.entity_description = ButtonEntityDescription(
            key="button",
            name=device.channel_name,
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

    async def async_press(self) -> None:
        """Handle the button press."""
        await self._device.press()
