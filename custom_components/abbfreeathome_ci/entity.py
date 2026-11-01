"""Shared entity helpers for the ABB-free@home integration."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from abbfreeathome import FreeAtHome
from abbfreeathome.channels.base import Base
from abbfreeathome.device import Device

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

type ChannelGetter = Callable[[type[Base]], list[Base]]
type EntityBuilder = Callable[[ChannelGetter], Iterable[Entity]]


@callback
def signal_channels_added(entry_id: str) -> str:
    """Return the dispatcher signal for channels added at runtime."""
    return f"{DOMAIN}_{entry_id}_channels_added"


@callback
def async_entity_is_loaded(hass: HomeAssistant, entity: Entity) -> bool:
    """Return True if the entity is currently added to Home Assistant."""
    return (
        entity.entity_id is not None and hass.states.get(entity.entity_id) is not None
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
    entities: dict[str | None, Entity] = {}

    def _track(new_entities: Iterable[Entity]) -> list[Entity]:
        result = []
        for entity in new_entities:
            existing = entities.get(entity.unique_id)
            if existing is not None and async_entity_is_loaded(hass, existing):
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
