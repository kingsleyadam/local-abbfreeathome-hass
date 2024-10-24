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
        FreeAtHomeButtonEntity(button, sysap_serial_number=entry.data[CONF_SERIAL])
        for button in free_at_home.get_device_by_class(device_class=Trigger)
    )


class FreeAtHomeButtonEntity(ButtonEntity):
    """Defines a Free@Home button entity."""

    _attr_should_poll: bool = False

    def __init__(self, button: Trigger, sysap_serial_number: str) -> None:
        """Initialize the button."""
        super().__init__()
        self._button = button
        self._sysap_serial_number = sysap_serial_number

        self.entity_description = ButtonEntityDescription(
            key="button",
            name=button.channel_name,
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._button.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._button.remove_callback(self.async_write_ha_state)

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._button.device_id)},
            "name": self._button.device_name,
            "manufacturer": "ABB busch-jaeger",
            "serial_number": self._button.device_id,
            "suggested_area": self._button.room_name,
            "via_device": (DOMAIN, self._sysap_serial_number),
        }

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._button.device_id}_{self._button.channel_id}_button"

    async def async_press(self) -> None:
        """Press the button."""
        await self._button.press()
