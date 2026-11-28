"""Shared entity helpers for the ABB-free@home integration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
import logging

from abbfreeathome import FreeAtHome
from abbfreeathome.bin.pairing import Pairing
from abbfreeathome.channels.base import Base
from abbfreeathome.device import Device
from abbfreeathome.exceptions import FreeAtHomeException, InvalidDeviceChannelPairing

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

type ChannelGetter = Callable[[type[Base]], list[Base]]
type EntityBuilder = Callable[[ChannelGetter], Iterable[FreeAtHomeEntity]]


@callback
def signal_channels_added(entry_id: str) -> str:
    """Return the dispatcher signal for channels added at runtime."""
    return f"{DOMAIN}_{entry_id}_channels_added"


@callback
def signal_devices_removed(entry_id: str) -> str:
    """Return the dispatcher signal for devices removed at runtime."""
    return f"{DOMAIN}_{entry_id}_devices_removed"


def _strip_device_name(name: str, device_name: str) -> str | None:
    """Return the name without the device name in front, or None if it is not.

    Follows Home Assistant's prefix stripping of legacy entity names: the
    device name matches case-insensitively and must be followed by a
    separator, and a lowercase first word of the rest is capitalized. Unlike
    Home Assistant, the comparison is per character, so a letter whose
    case-folded form has another length, such as "ß" and "SS", does not match.
    An empty device name is no prefix; it would match an empty name forever.
    """
    if not device_name or name[: len(device_name)].casefold() != device_name.casefold():
        return None
    rest = name[len(device_name) :].lstrip(" -:")
    if not rest:
        return ""
    if len(rest) == len(name) - len(device_name):
        return None
    if rest.partition(" ")[0].islower():
        return rest[0].upper() + rest[1:]
    return rest


def channel_entity_name(channel: Base, create_subdevices: bool) -> str | None:
    """Return the name of an entity named after its channel.

    Home Assistant shows the device name in front of the entity name, so the
    device name is removed from the start of the channel name, repeatedly
    because the SysAP may repeat it, as in "Switch 2 Switch 2 Left". If
    nothing is left, the channel is the device's main feature and the entity
    has no name of its own. A sub-device has a name of its own with the
    channel ID, not the device name, so there the channel name is kept.
    """
    name = channel.channel_name
    if create_subdevices and channel.device.is_multi_device:
        return name
    while (stripped := _strip_device_name(name, channel.device_name)) is not None:
        name = stripped
    return name or None


def main_feature_name(channel: Base, create_subdevices: bool) -> str | None:
    """Return the name of a channel's main feature that has a translated name.

    The main feature, such as a window contact or a heating valve, is named
    after its channel like an entity without a translated name, so the
    channels of a multi-channel device can be told apart. On a channel without
    a name of its own, one named like its device, this returns None and the
    translated name, such as "Window", applies, also on a sub-device.
    """
    if channel_entity_name(channel, create_subdevices=False) is None:
        return None
    return channel_entity_name(channel, create_subdevices)


def channel_has_output(channel: Base, pairing: Pairing) -> bool:
    """Return whether the channel has the output with the pairing."""
    try:
        channel.get_output_by_pairing(pairing)
    except InvalidDeviceChannelPairing:
        return False
    return True


@callback
def async_release_removed_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    entities: dict[str | None, FreeAtHomeEntity],
) -> None:
    """Forget tracked entities of removed devices so they can be added again."""

    @callback
    def _async_devices_removed(device_serials: tuple[str, ...]) -> None:
        for unique_id, entity in list(entities.items()):
            if entity.device_serial in device_serials:
                del entities[unique_id]

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, signal_devices_removed(entry.entry_id), _async_devices_removed
        )
    )


@callback
def async_setup_platform_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    build_entities: EntityBuilder,
) -> None:
    """Add entities for current channels and for channels added at runtime.

    build_entities receives a callable returning the channels of a given class,
    so the same platform logic is used at startup and for runtime additions.
    """
    free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]
    # Reserved when queued, so a repeat notification before the entity has been
    # added to Home Assistant cannot queue a duplicate.
    entities: dict[str | None, FreeAtHomeEntity] = {}

    def _track(new_entities: Iterable[FreeAtHomeEntity]) -> list[FreeAtHomeEntity]:
        result = []
        for entity in new_entities:
            if entity.unique_id in entities:
                continue
            entities[entity.unique_id] = entity
            result.append(entity)
        return result

    async_add_entities(
        _track(
            build_entities(
                lambda channel_class: free_at_home.get_channels_by_class(
                    channel_class=channel_class
                )
            )
        )
    )

    @callback
    def _async_channels_added(channels: tuple[Base, ...]) -> None:
        def _get_channels(channel_class: type[Base]) -> list[Base]:
            return [channel for channel in channels if type(channel) is channel_class]

        if new_entities := _track(build_entities(_get_channels)):
            async_add_entities(new_entities)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, signal_channels_added(entry.entry_id), _async_channels_added
        )
    )
    async_release_removed_entities(hass, entry, entities)


class FreeAtHomeEntity(Entity):
    """Base for entities backed by a free@home device.

    Entities are marked unavailable while their device is unresponsive.
    """

    _channel: Base

    @property
    def _free_at_home_device(self) -> Device:
        """Return the free@home device backing this entity."""
        return self._channel.device

    @property
    def device_serial(self) -> str:
        """Return the serial of the free@home device backing this entity."""
        return self._free_at_home_device.device_serial

    @property
    def available(self) -> bool:
        """Return True if the backing device is responsive."""
        return not self._free_at_home_device.unresponsive

    async def async_added_to_hass(self) -> None:
        """Subscribe to device availability changes."""
        await super().async_added_to_hass()
        device = self._free_at_home_device
        device.register_unresponsive_callback(self.async_write_ha_state)
        self.async_on_remove(
            lambda: device.remove_unresponsive_callback(self.async_write_ha_state)
        )

    async def _async_refresh_channel(self, attribute: str | None = None) -> None:
        """Refresh the channel, or one of its attributes, from the SysAP.

        For an attribute, channels that map their attributes to datapoints,
        such as wind and air quality sensors, read only the attribute's
        datapoints; otherwise all datapoints of the channel are read. Library
        errors, such as an unreachable SysAP, values the channel rejects, and
        request timeouts are logged as a warning without a traceback; debug
        logging adds the traceback.
        """
        try:
            await self._channel.refresh_state(
                attributes=None if attribute is None else [attribute]
            )
        # Channels raise ValueError for values they reject, such as a virtual
        # dimmer's brightness outside 0-100 percent.
        except (FreeAtHomeException, ValueError) as err:
            _LOGGER.warning(
                "Could not refresh %s from the SysAP: %s", self.entity_id, err
            )
            _LOGGER.debug("Refresh of %s failed", self.entity_id, exc_info=True)
        except TimeoutError:
            # aiohttp raises its total request timeout as plain TimeoutError.
            _LOGGER.warning(
                "Could not refresh %s from the SysAP: request timed out",
                self.entity_id,
            )
            _LOGGER.debug("Refresh of %s failed", self.entity_id, exc_info=True)
