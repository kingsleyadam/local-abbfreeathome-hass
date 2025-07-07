"""Create ABB-free@home button entities."""

from abbfreeathome import FreeAtHome
from abbfreeathome.channels.trigger import Trigger

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CREATE_SUBDEVICES, CONF_SERIAL, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up buttons."""
    free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        FreeAtHomeButtonEntity(
            channel,
            sysap_serial_number=entry.data[CONF_SERIAL],
            hass=hass,
            create_subdevices=entry.data[CONF_CREATE_SUBDEVICES],
            config_entry_id=entry.entry_id,
        )
        for channel in free_at_home.get_channels_by_class(channel_class=Trigger)
    )


class FreeAtHomeButtonEntity(ButtonEntity):
    """Defines a free@home button entity."""

    _attr_should_poll: bool = False

    def __init__(
        self,
        channel: Trigger,
        sysap_serial_number: str,
        hass: HomeAssistant,
        create_subdevices: bool,
        config_entry_id: str,
    ) -> None:
        """Initialize the button."""
        super().__init__()
        self._channel = channel
        self._sysap_serial_number = sysap_serial_number
        self._create_subdevices = create_subdevices

        self.entity_description = ButtonEntityDescription(
            key="button",
            name=channel.channel_name,
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
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._channel.device_serial}_{self._channel.channel_id}_button"

    async def async_press(self) -> None:
        """Press the button."""
        await self._channel.press()
