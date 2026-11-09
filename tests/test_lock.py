"""Test ABB-free@home lock."""

from unittest.mock import MagicMock, call

from abbfreeathome.bin.pairing import Pairing
from abbfreeathome.channels.des_door_opener_actuator import DesDoorOpenerActuator
from abbfreeathome.device import Device
import pytest
from syrupy.assertion import SnapshotAssertion

from custom_components.abbfreeathome_ci.const import CONF_CREATE_SUBDEVICES, DOMAIN
from homeassistant.components.homeassistant import (
    DOMAIN as HOMEASSISTANT_DOMAIN,
    SERVICE_UPDATE_ENTITY,
)
from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN, LockState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_LOCK,
    SERVICE_UNLOCK,
    STATE_UNKNOWN,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

from .common import (
    MockConfigEntry,
    build_channel,
    build_device,
    setup_with_channels,
    snapshot_entities,
)

SERIAL = "ABB700000001"


@pytest.fixture(autouse=True)
def lock_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load only the lock platform."""
    monkeypatch.setattr("custom_components.abbfreeathome_ci.PLATFORMS", [Platform.LOCK])


def _build_door_opener(
    device: Device, channel_id: str = "ch0000", state: str | None = "0"
) -> DesDoorOpenerActuator:
    """Build a real door opener channel, locked by default.

    Unlocking and locking set the AL_TIMED_START_STOP input (idp0000) to 1
    and 0. The SysAP reports the state on the AL_INFO_ON_OFF output
    (odp0000), 1 while the door is unlocked; without it, the state is
    unknown.
    """
    return build_channel(
        DesDoorOpenerActuator,
        device,
        channel_id,
        inputs={Pairing.AL_TIMED_START_STOP: "0"},
        outputs={} if state is None else {Pairing.AL_INFO_ON_OFF: state},
    )


def _entity_id(entity_registry: er.EntityRegistry, channel_id: str = "ch0000") -> str:
    """Return the entity ID of the lock of a door opener by its unique ID."""
    # Unique IDs must never change; locks keep the legacy suffix "valve".
    entity_id = entity_registry.async_get_entity_id(
        LOCK_DOMAIN, DOMAIN, f"{SERIAL}_{channel_id}_valve"
    )
    assert entity_id is not None
    return entity_id


async def test_lock_entity(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the lock entity of a door opener."""
    await setup_with_channels(
        hass,
        mock_config_entry,
        mock_free_at_home_settings,
        [_build_door_opener(build_device(SERIAL))],
    )

    snapshot_entities(hass, snapshot, mock_config_entry.entry_id)


@pytest.mark.parametrize(
    ("state", "expected"),
    [("0", LockState.LOCKED), ("1", LockState.UNLOCKED), (None, STATE_UNKNOWN)],
    ids=["locked", "unlocked", "unknown"],
)
async def test_lock_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    state: str | None,
    expected: str,
) -> None:
    """Test the door is locked while the door opener is off, unknown without state."""
    await setup_with_channels(
        hass,
        mock_config_entry,
        mock_free_at_home_settings,
        [_build_door_opener(build_device(SERIAL), state=state)],
    )

    assert hass.states.get(_entity_id(entity_registry)).state == expected


async def test_lock_follows_sysap(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test a lock shows the state the SysAP reports without a command."""
    device = build_device(SERIAL)
    channel = _build_door_opener(device)
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry)

    channel.update_channel(f"{SERIAL}/ch0000/odp0000", "1")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == LockState.UNLOCKED

    channel.update_channel(f"{SERIAL}/ch0000/odp0000", "0")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == LockState.LOCKED
    device.api.set_datapoint.assert_not_awaited()


async def test_lock_unlock_lock(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test unlocking and locking set the door opener's input on the SysAP."""
    device = build_device(SERIAL)
    await setup_with_channels(
        hass,
        mock_config_entry,
        mock_free_at_home_settings,
        [_build_door_opener(device)],
    )
    entity_id = _entity_id(entity_registry)

    await hass.services.async_call(
        LOCK_DOMAIN, SERVICE_UNLOCK, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    await hass.services.async_call(
        LOCK_DOMAIN, SERVICE_LOCK, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )

    datapoint = {
        "device_serial": SERIAL,
        "channel_id": "ch0000",
        "datapoint": "idp0000",
    }
    assert device.api.set_datapoint.await_args_list == [
        call(**datapoint, value="1"),
        call(**datapoint, value="0"),
    ]


async def test_lock_update_entity(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test updating a lock refreshes its state from the SysAP."""
    assert await async_setup_component(hass, HOMEASSISTANT_DOMAIN, {})
    device = build_device(SERIAL)
    await setup_with_channels(
        hass,
        mock_config_entry,
        mock_free_at_home_settings,
        [_build_door_opener(device)],
    )
    entity_id = _entity_id(entity_registry)
    device.api.get_datapoint.return_value = ["1"]

    await hass.services.async_call(
        HOMEASSISTANT_DOMAIN,
        SERVICE_UPDATE_ENTITY,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    assert hass.states.get(entity_id).state == LockState.UNLOCKED
    device.api.get_datapoint.assert_awaited_once_with(
        device_serial=SERIAL, channel_id="ch0000", datapoint="odp0000"
    )


async def test_lock_removes_callback_on_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test an unloaded lock no longer follows its door opener."""
    channel = _build_door_opener(build_device(SERIAL))
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry)

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)

    channel.update_channel(f"{SERIAL}/ch0000/odp0000", "1")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id) == state
    assert channel._callbacks == {"state": set()}


@pytest.mark.parametrize(
    ("create_subdevices", "multi_device_identifier"),
    [
        (False, (DOMAIN, SERIAL)),
        (True, (DOMAIN, f"{SERIAL}_ch0000")),
    ],
)
async def test_lock_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    create_subdevices: bool,
    multi_device_identifier: tuple[str, str],
) -> None:
    """Test a lock of a multi-channel device belongs to a subdevice if enabled."""
    entry = MockConfigEntry(
        version=mock_config_entry.version,
        minor_version=mock_config_entry.minor_version,
        domain=DOMAIN,
        title=mock_config_entry.title,
        data={**mock_config_entry.data, CONF_CREATE_SUBDEVICES: create_subdevices},
        source=mock_config_entry.source,
        unique_id=mock_config_entry.unique_id,
    )
    # A device without a room and with several channels is a multi-device.
    multi_device = build_device(SERIAL)
    multi_channel = _build_door_opener(multi_device)
    _build_door_opener(multi_device, "ch0001")
    assert multi_device.is_multi_device
    single_device = build_device("ABB700000002")
    single_channel = _build_door_opener(single_device)
    assert not single_device.is_multi_device

    await setup_with_channels(
        hass, entry, mock_free_at_home_settings, [multi_channel, single_channel]
    )

    def device_identifiers(unique_id: str) -> set[tuple[str, str]]:
        """Return the identifiers of the device of a lock."""
        entity_id = entity_registry.async_get_entity_id(LOCK_DOMAIN, DOMAIN, unique_id)
        entity_entry = entity_registry.async_get(entity_id)
        return device_registry.async_get(entity_entry.device_id).identifiers

    assert device_identifiers(f"{SERIAL}_ch0000_valve") == {multi_device_identifier}
    assert device_identifiers("ABB700000002_ch0000_valve") == {(DOMAIN, "ABB700000002")}
