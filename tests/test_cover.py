"""Test ABB-free@home cover."""

from dataclasses import dataclass
from unittest.mock import MagicMock, call

from abbfreeathome.bin.pairing import Pairing
from abbfreeathome.channels.cover_actuator import (
    AtticWindowActuator,
    AwningActuator,
    BlindActuator,
    CoverActuator,
    ShutterActuator,
)
from abbfreeathome.device import Device
import pytest
from syrupy.assertion import SnapshotAssertion

from custom_components.abbfreeathome_ci.const import CONF_CREATE_SUBDEVICES, DOMAIN
from custom_components.abbfreeathome_ci.cover import COVER_DESCRIPTIONS
from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_CURRENT_TILT_POSITION,
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    DOMAIN as COVER_DOMAIN,
    CoverState,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_SET_COVER_POSITION,
    SERVICE_SET_COVER_TILT_POSITION,
    SERVICE_STOP_COVER,
    STATE_UNKNOWN,
    Platform,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .common import (
    MockConfigEntry,
    build_channel,
    build_device,
    setup_with_channels,
    snapshot_entities,
)

SERIAL = "ABB700000001"

# Opening and closing set the move input, stopping the stop input, and
# positioning the position input; shutters also have an input for their slats.
MOVE_INPUT = "idp0000"
STOP_INPUT = "idp0001"
POSITION_INPUT = "idp0002"
TILT_INPUT = "idp0003"
COVER_INPUTS = {
    Pairing.AL_MOVE_UP_DOWN: "0",
    Pairing.AL_STOP_STEP_UP_DOWN: "0",
    Pairing.AL_SET_ABSOLUTE_POSITION_BLINDS_PERCENTAGE: "30",
}
SHUTTER_INPUTS = COVER_INPUTS | {
    Pairing.AL_SET_ABSOLUTE_POSITION_SLATS_PERCENTAGE: "25"
}

# The SysAP reports whether a cover moves, its position, and the position of
# a shutter's slats.
MOVEMENT_OUTPUT = "odp0000"
POSITION_OUTPUT = "odp0001"
TILT_OUTPUT = "odp0002"


@dataclass(frozen=True)
class CoverCase:
    """A cover description with a real channel.

    The SysAP counts positions from 0 (open) to 100 (closed), the other way
    round than Home Assistant. Awnings count from 0 (retracted) and report
    their movement the other way round as well; the library inverts both, so
    Home Assistant shows an awning like any other cover.
    """

    channel_class: type[CoverActuator]
    channel_id: str
    # The reported position of a closed cover.
    closed: str = "100"
    # The reported movement while the cover opens and while it closes.
    opening: str = "2"
    closing: str = "3"
    # The position Home Assistant shows for the reported position 30.
    position: int = 70
    # Opening and closing set the move input; awnings set their position.
    open_command: tuple[str, str] = (MOVE_INPUT, "0")
    close_command: tuple[str, str] = (MOVE_INPUT, "1")
    # The position that sets Home Assistant's position 30.
    position_command: str = "70"
    # Only shutters have slats.
    tilt: bool = False


# Unique IDs must never change; each ends with the description's key.
COVER_CASES = {
    "AtticWindowActuator": CoverCase(AtticWindowActuator, "ch0000"),
    "AwningActuator": CoverCase(
        AwningActuator,
        "ch0001",
        closed="0",
        opening="3",
        closing="2",
        position=30,
        open_command=(POSITION_INPUT, "100"),
        close_command=(POSITION_INPUT, "0"),
        position_command="30",
    ),
    "BlindActuator": CoverCase(BlindActuator, "ch0002"),
    "ShutterActuator": CoverCase(ShutterActuator, "ch0003", tilt=True),
}


@pytest.fixture(autouse=True)
def cover_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load only the cover platform."""
    monkeypatch.setattr(
        "custom_components.abbfreeathome_ci.PLATFORMS", [Platform.COVER]
    )


def test_cases_cover_all_descriptions() -> None:
    """Test every cover description has a case with its channel class."""
    assert list(COVER_CASES) == list(COVER_DESCRIPTIONS)
    for key, case in COVER_CASES.items():
        assert case.channel_class is COVER_DESCRIPTIONS[key]["channel_class"]


def _build_cover(device: Device, key: str, movement: str = "1") -> CoverActuator:
    """Build the real channel of a cover case at the reported position 30.

    The movement 1 means the cover stands partly open. Shutters also report
    their slats at 25.
    """
    case = COVER_CASES[key]
    outputs = {
        Pairing.AL_INFO_MOVE_UP_DOWN: movement,
        Pairing.AL_CURRENT_ABSOLUTE_POSITION_BLINDS_PERCENTAGE: "30",
    }
    if case.tilt:
        outputs[Pairing.AL_CURRENT_ABSOLUTE_POSITION_SLATS_PERCENTAGE] = "25"
    return build_channel(
        case.channel_class,
        device,
        case.channel_id,
        inputs=SHUTTER_INPUTS if case.tilt else COVER_INPUTS,
        outputs=outputs,
    )


def _entity_id(entity_registry: er.EntityRegistry, key: str) -> str:
    """Return the entity ID of a cover case by its unique ID."""
    entity_id = entity_registry.async_get_entity_id(
        COVER_DOMAIN, DOMAIN, f"{SERIAL}_{COVER_CASES[key].channel_id}_{key}"
    )
    assert entity_id is not None
    return entity_id


async def test_cover_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the cover entities of all descriptions, partly open."""
    device = build_device(SERIAL)

    await setup_with_channels(
        hass,
        mock_config_entry,
        mock_free_at_home_settings,
        [_build_cover(device, key) for key in COVER_CASES],
    )

    snapshot_entities(hass, snapshot, mock_config_entry.entry_id)
    for key, case in COVER_CASES.items():
        state = hass.states.get(_entity_id(entity_registry, key))
        assert state.state == CoverState.OPEN
        assert state.attributes[ATTR_CURRENT_POSITION] == case.position


@pytest.mark.parametrize("key", COVER_CASES)
async def test_cover_follows_sysap(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    key: str,
) -> None:
    """Test a cover shows the position and movement the SysAP reports."""
    case = COVER_CASES[key]
    device = build_device(SERIAL)
    channel = _build_cover(device, key)
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, key)

    async def report(datapoint: str, value: str) -> State:
        """Report a datapoint value and return the state of the cover."""
        channel.update_channel(f"{SERIAL}/{case.channel_id}/{datapoint}", value)
        await hass.async_block_till_done()
        return hass.states.get(entity_id)

    state = await report(POSITION_OUTPUT, case.closed)
    assert state.state == CoverState.CLOSED
    assert state.attributes[ATTR_CURRENT_POSITION] == 0
    assert (await report(MOVEMENT_OUTPUT, case.opening)).state == CoverState.OPENING
    assert (await report(MOVEMENT_OUTPUT, case.closing)).state == CoverState.CLOSING
    device.api.set_datapoint.assert_not_awaited()


@pytest.mark.parametrize("key", COVER_CASES)
async def test_cover_commands(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    key: str,
) -> None:
    """Test opening, closing, positioning, and stopping a cover on the SysAP."""
    case = COVER_CASES[key]
    device = build_device(SERIAL)
    # The library stops only a moving cover.
    channel = _build_cover(device, key, movement=case.opening)
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, key)

    for service, data in (
        (SERVICE_OPEN_COVER, {}),
        (SERVICE_CLOSE_COVER, {}),
        (SERVICE_SET_COVER_POSITION, {ATTR_POSITION: 30}),
        (SERVICE_STOP_COVER, {}),
    ):
        await hass.services.async_call(
            COVER_DOMAIN, service, {ATTR_ENTITY_ID: entity_id, **data}, blocking=True
        )

    def command(datapoint: str, value: str):
        """Return the call that sets a datapoint of the cover."""
        return call(
            device_serial=SERIAL,
            channel_id=case.channel_id,
            datapoint=datapoint,
            value=value,
        )

    assert device.api.set_datapoint.await_args_list == [
        command(*case.open_command),
        command(*case.close_command),
        command(POSITION_INPUT, case.position_command),
        command(STOP_INPUT, "1"),
    ]


async def test_shutter_tilt_follows_sysap(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test a shutter shows the slat position the SysAP reports."""
    device = build_device(SERIAL)
    channel = _build_cover(device, "ShutterActuator")
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, "ShutterActuator")
    assert hass.states.get(entity_id).attributes[ATTR_CURRENT_TILT_POSITION] == 75

    channel.update_channel(f"{SERIAL}/ch0003/{TILT_OUTPUT}", "100")
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).attributes[ATTR_CURRENT_TILT_POSITION] == 0
    device.api.set_datapoint.assert_not_awaited()


async def test_shutter_set_tilt_position(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test tilting a shutter sets the position of its slats on the SysAP."""
    device = build_device(SERIAL)
    await setup_with_channels(
        hass,
        mock_config_entry,
        mock_free_at_home_settings,
        [_build_cover(device, "ShutterActuator")],
    )

    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_SET_COVER_TILT_POSITION,
        {
            ATTR_ENTITY_ID: _entity_id(entity_registry, "ShutterActuator"),
            ATTR_TILT_POSITION: 20,
        },
        blocking=True,
    )

    device.api.set_datapoint.assert_awaited_once_with(
        device_serial=SERIAL, channel_id="ch0003", datapoint=TILT_INPUT, value="80"
    )


async def test_cover_without_reported_positions(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test a cover is unknown without a position and has no tilt without one."""
    device = build_device(SERIAL)
    blind = build_channel(
        BlindActuator,
        device,
        "ch0002",
        inputs=COVER_INPUTS,
        outputs={Pairing.AL_INFO_MOVE_UP_DOWN: "1"},
    )
    shutter = build_channel(
        ShutterActuator,
        device,
        "ch0003",
        inputs=SHUTTER_INPUTS,
        outputs={
            Pairing.AL_INFO_MOVE_UP_DOWN: "1",
            Pairing.AL_CURRENT_ABSOLUTE_POSITION_BLINDS_PERCENTAGE: "30",
        },
    )

    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [blind, shutter]
    )

    blind_state = hass.states.get(_entity_id(entity_registry, "BlindActuator"))
    assert blind_state.state == STATE_UNKNOWN
    assert ATTR_CURRENT_POSITION not in blind_state.attributes
    shutter_state = hass.states.get(_entity_id(entity_registry, "ShutterActuator"))
    assert shutter_state.state == CoverState.OPEN
    assert ATTR_CURRENT_TILT_POSITION not in shutter_state.attributes


@pytest.mark.parametrize(
    ("key", "attributes"),
    [
        ("BlindActuator", {"state", "position"}),
        ("ShutterActuator", {"state", "position", "tilt_position"}),
    ],
)
async def test_cover_removes_callbacks_on_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    key: str,
    attributes: set[str],
) -> None:
    """Test an unloaded cover no longer follows its channel."""
    case = COVER_CASES[key]
    channel = _build_cover(build_device(SERIAL), key)
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, key)

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)

    channel.update_channel(f"{SERIAL}/{case.channel_id}/{POSITION_OUTPUT}", "100")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id) == state
    assert channel._callbacks == {attribute: set() for attribute in attributes}


@pytest.mark.parametrize(
    ("create_subdevices", "multi_device_identifier"),
    [
        (False, (DOMAIN, SERIAL)),
        (True, (DOMAIN, f"{SERIAL}_ch0002")),
    ],
)
async def test_cover_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    create_subdevices: bool,
    multi_device_identifier: tuple[str, str],
) -> None:
    """Test a cover of a multi-channel device belongs to a subdevice if enabled."""
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
    multi_channel = _build_cover(multi_device, "BlindActuator")
    _build_cover(multi_device, "ShutterActuator")
    assert multi_device.is_multi_device
    single_device = build_device("ABB700000002")
    single_channel = _build_cover(single_device, "BlindActuator")
    assert not single_device.is_multi_device

    await setup_with_channels(
        hass, entry, mock_free_at_home_settings, [multi_channel, single_channel]
    )

    def device_identifiers(unique_id: str) -> set[tuple[str, str]]:
        """Return the identifiers of the device of a cover."""
        entity_id = entity_registry.async_get_entity_id(COVER_DOMAIN, DOMAIN, unique_id)
        entity_entry = entity_registry.async_get(entity_id)
        return device_registry.async_get(entity_entry.device_id).identifiers

    assert device_identifiers(f"{SERIAL}_ch0002_BlindActuator") == {
        multi_device_identifier
    }
    assert device_identifiers("ABB700000002_ch0002_BlindActuator") == {
        (DOMAIN, "ABB700000002")
    }
