"""Shared test helpers, including those of the installed Home Assistant plugin."""

from collections.abc import Iterable, Mapping
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from abbfreeathome import DevicesChangedEvent
from abbfreeathome.api import FreeAtHomeApi
from abbfreeathome.bin.interface import Interface
from abbfreeathome.bin.pairing import Pairing
from abbfreeathome.bin.parameter import Parameter
from abbfreeathome.channels.base import Base
from abbfreeathome.channels.trigger import Trigger
from abbfreeathome.device import Device
from syrupy.assertion import SnapshotAssertion

from custom_components.abbfreeathome_ci.const import DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
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
    from pytest_homeassistant.syrupy import HomeAssistantSnapshotExtension
except ImportError:
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        MockEntityPlatform,
        MockPlatform,
        async_fire_time_changed,
    )
    from pytest_homeassistant_custom_component.syrupy import (
        HomeAssistantSnapshotExtension,
    )

__all__ = [
    "HomeAssistantSnapshotExtension",
    "MockConfigEntry",
    "async_fire_time_changed",
    "async_setup_entity_platform",
    "build_channel",
    "build_device",
    "build_trigger",
    "devices_changed",
    "get_device_entry",
    "setup_with_channels",
    "snapshot_entities",
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


async def setup_with_channels(
    hass: HomeAssistant,
    entry: ConfigEntry,
    settings: MagicMock,
    channels: list[Base],
    *,
    devices: Iterable[Device] = (),
) -> MagicMock:
    """Set up the integration with a mocked FreeAtHome holding mutable channels.

    Only the SysAP connection is mocked: the integration sets up the entry
    through Home Assistant and builds its entities from the given library
    channels. Append to the returned mock's channels and call
    devices_changed() to add channels at runtime. devices adds devices
    without visible channels, such as a device whose channels are all
    filtered out.
    """
    devices = tuple(devices)

    async def ws_listen_coro():
        """Mock coroutine for ws_listen."""

    mock_fah = MagicMock()
    mock_fah.channels = channels
    mock_fah.get_config = AsyncMock()
    mock_fah.load = AsyncMock()
    mock_fah.ws_listen = MagicMock(side_effect=ws_listen_coro)
    mock_fah.ws_close = AsyncMock()
    mock_fah.get_devices = MagicMock(
        side_effect=lambda: {
            **{device.device_serial: device for device in devices},
            **{channel.device_serial: channel.device for channel in channels},
        }
    )
    mock_fah.get_channels_by_device = MagicMock(
        side_effect=lambda serial: [c for c in channels if c.device_serial == serial]
    )
    # Match the exact class, like FreeAtHome.get_channels_by_class().
    mock_fah.get_channels_by_class = MagicMock(
        side_effect=lambda channel_class: [
            c for c in channels if type(c) is channel_class
        ]
    )
    if hass.config_entries.async_get_entry(entry.entry_id) is None:
        entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHomeSettings",
            return_value=settings,
        ),
        patch("custom_components.abbfreeathome_ci.FreeAtHome", return_value=mock_fah),
        patch("custom_components.abbfreeathome_ci.FreeAtHomeApi"),
        patch("custom_components.abbfreeathome_ci.async_get_clientsession"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return mock_fah


def build_device(
    serial: str = "ABB700000001",
    *,
    display_name: str = "Runtime Device",
    room_name: str | None = "Hall",
    parameters: dict[str, Any] | None = None,
    interface: Interface | None = None,
    unresponsive: bool = False,
) -> Device:
    """Build a real free@home device with a mocked API.

    The API mock has the spec of FreeAtHomeApi, so its coroutine methods,
    such as set_datapoint, are AsyncMock objects to assert commands on.
    """
    return Device(
        serial,
        "1234",
        display_name,
        api=MagicMock(spec=FreeAtHomeApi),
        interface=interface,
        unresponsive=unresponsive,
        room_name=room_name,
        parameters=parameters,
    )


def _datapoints(prefix: str, values: Mapping[Pairing, str]) -> dict[str, dict]:
    """Return channel datapoints numbered in order, such as idp0000."""
    return {
        f"{prefix}{index:04x}": {"pairingID": pairing.value, "value": value}
        for index, (pairing, value) in enumerate(values.items())
    }


def build_channel[ChannelT: Base](
    channel_class: type[ChannelT],
    device: Device,
    channel_id: str = "ch0000",
    *,
    channel_name: str | None = None,
    inputs: Mapping[Pairing, str] | None = None,
    outputs: Mapping[Pairing, str] | None = None,
    parameters: Mapping[Parameter, str] | None = None,
) -> ChannelT:
    """Build a real library channel and add it to its device.

    Inputs and outputs map pairings to datapoint values; they get the IDs
    idp0000, idp0001, ... and odp0000, odp0001, ... in the given order.
    The channel name defaults to the class name and the channel ID.
    """
    channel = channel_class(
        device,
        channel_id,
        channel_name or f"{channel_class.__name__} {channel_id}",
        _datapoints("idp", inputs or {}),
        _datapoints("odp", outputs or {}),
        {
            f"par{parameter.value:04x}": value
            for parameter, value in (parameters or {}).items()
        },
        room_name=device.room_name,
    )
    device.channels[channel_id] = channel
    return channel


def build_trigger(
    device: Device, channel_id: str = "ch0000", parameters=None
) -> Trigger:
    """Build a real Trigger channel (button entity)."""
    return Trigger(
        device, channel_id, f"Trigger {channel_id}", {}, {}, parameters or {}
    )


def devices_changed(mock_fah: MagicMock, event: DevicesChangedEvent) -> None:
    """Invoke the devices-changed callback the integration registered."""
    mock_fah.register_devices_changed_callback.call_args.args[0](event)


def get_device_entry(
    hass: HomeAssistant, config_entry_id: str, serial: str
) -> dr.DeviceEntry | None:
    """Return the device a config entry registered for a serial.

    HA 2026.8 deprecated async_get_device in favor of
    async_get_device_by_identifier; older versions only have async_get_device.
    """
    device_registry = dr.async_get(hass)
    # compat: homeassistant<2026.8 - async_get_device_by_identifier replaced async_get_device
    if not hasattr(device_registry, "async_get_device_by_identifier"):
        return device_registry.async_get_device(identifiers={(DOMAIN, serial)})
    return device_registry.async_get_device_by_identifier(
        (DOMAIN, serial), config_entry_id
    )


def _str_unit(unit: str | None) -> str | None:
    """Return a unit of measurement as a plain string.

    Releases differ in using enum members or strings for units, for example
    for parts per million before UnitOfRatio.
    """
    return None if unit is None else str(unit)


def snapshot_entities(
    hass: HomeAssistant, snapshot: SnapshotAssertion, config_entry_id: str
) -> None:
    """Snapshot the registry entries and states of a config entry's entities.

    Unlike snapshot_platform() of the Home Assistant plugin, this keeps only
    what the integration decides, so one snapshot fits every Home Assistant
    version in the test matrix: Home Assistant serializes registry entries
    differently between versions and builds entity IDs differently, for
    example with the area. The snapshots are named by unique ID for the same
    reason, and keys and units are compared as strings.
    """
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    entity_entries = er.async_entries_for_config_entry(entity_registry, config_entry_id)
    assert entity_entries
    for entity_entry in sorted(entity_entries, key=lambda entry: entry.unique_id):
        assert entity_entry.disabled_by is None, "Please enable all entities."
        state = hass.states.get(entity_entry.entity_id)
        assert state, f"State not found for {entity_entry.entity_id}"
        device_entry = device_registry.async_get(entity_entry.device_id)
        attributes = _str_keys(state.attributes)
        if ATTR_UNIT_OF_MEASUREMENT in attributes:
            attributes[ATTR_UNIT_OF_MEASUREMENT] = _str_unit(
                attributes[ATTR_UNIT_OF_MEASUREMENT]
            )
        assert {
            "domain": entity_entry.domain,
            "device": sorted(device_entry.identifiers) if device_entry else None,
            "original_name": entity_entry.original_name,
            "translation_key": entity_entry.translation_key,
            "has_entity_name": entity_entry.has_entity_name,
            "original_device_class": entity_entry.original_device_class,
            "original_icon": entity_entry.original_icon,
            "entity_category": entity_entry.entity_category,
            "capabilities": _str_keys(entity_entry.capabilities),
            "supported_features": entity_entry.supported_features,
            "unit_of_measurement": _str_unit(entity_entry.unit_of_measurement),
            "state": state.state,
            "attributes": attributes,
        } == snapshot(name=entity_entry.unique_id)


def _str_keys(mapping: Mapping[Any, Any] | None) -> dict[str, Any] | None:
    """Return a mapping with string keys.

    Home Assistant releases differ in using enum members or strings as keys,
    for example for the event types an event entity has.
    """
    if mapping is None:
        return None
    return {str(key): value for key, value in mapping.items()}
