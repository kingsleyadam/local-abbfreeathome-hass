"""Shared entity helpers for the ABB-free@home integration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
import logging

from abbfreeathome import FreeAtHome
from abbfreeathome.channels.base import Base
from abbfreeathome.device import Device
from abbfreeathome.exceptions import FreeAtHomeException

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

    async def _async_refresh_channel(self) -> None:
        """Refresh the channel's values from the SysAP.

        Library errors, such as an unreachable SysAP or a datapoint the channel
        lacks, are logged as a warning without a traceback.
        """
        try:
            await self._channel.refresh_state()
        except FreeAtHomeException as err:
            _LOGGER.warning(
                "Could not refresh %s from the SysAP: %s", self.entity_id, err
            )
