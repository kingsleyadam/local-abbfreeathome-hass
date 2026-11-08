"""Test helpers from the installed Home Assistant pytest plugin."""

from collections.abc import Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback, EntityPlatform

# compat: homeassistant<2026.11 - pytest-homeassistant replaced pytest-homeassistant-custom-component
try:
    from pytest_homeassistant.common import (
        MockConfigEntry,
        MockEntityPlatform,
        MockPlatform,
        async_fire_time_changed,
    )
except ImportError:
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        MockEntityPlatform,
        MockPlatform,
        async_fire_time_changed,
    )

__all__ = [
    "MockConfigEntry",
    "async_fire_time_changed",
    "async_setup_entity_platform",
]


async def async_setup_entity_platform(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    domain: str,
    entities: Iterable[Entity],
) -> EntityPlatform:
    """Add entities to Home Assistant on an entity platform of the config entry.

    Only an entity of a config entry may link a device, so entities with
    device info need one; adding them without one is deprecated.
    """

    async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
    ) -> None:
        """Add the entities."""
        async_add_entities(entities)

    platform = MockEntityPlatform(
        hass,
        domain=domain,
        platform_name=config_entry.domain,
        platform=MockPlatform(async_setup_entry=async_setup_entry),
    )
    assert await platform.async_setup_entry(config_entry)
    return platform
