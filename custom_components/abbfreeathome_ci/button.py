"""Create ABB-free@home button entities."""

from abbfreeathome import FreeAtHome
from abbfreeathome.channels.trigger import Trigger

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CREATE_SUBDEVICES, CONF_SERIAL, DOMAIN, MANUFACTURER


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
            create_subdevices=entry.data[CONF_CREATE_SUBDEVICES],
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
        create_subdevices: bool,
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

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        if self._create_subdevices and self._channel.device.is_multi_device:
            return DeviceInfo(
                identifiers={
                    (
                        DOMAIN,
                        f"{self._channel.device_serial}_{self._channel.channel_id}",
                    )
                },
                name=f"{self._channel.device_name} ({self._channel.channel_id})",
                manufacturer=MANUFACTURER,
                serial_number=f"{self._channel.device_serial}_{self._channel.channel_id}",
                hw_version=f"{self._channel.device.device_id} (sub)",
                suggested_area=self._channel.room_name,
                via_device=(DOMAIN, self._channel.device_serial),
            )

        return DeviceInfo(identifiers={(DOMAIN, self._channel.device_serial)})

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._channel.device_serial}_{self._channel.channel_id}_button"

    async def async_press(self) -> None:
        """Press the button."""
        await self._channel.press()
