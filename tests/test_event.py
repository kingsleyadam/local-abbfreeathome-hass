"""Test ABB-free@home event."""

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any
from unittest.mock import MagicMock

from abbfreeathome.bin.pairing import Pairing
from abbfreeathome.channels.base import Base
from abbfreeathome.channels.blind_sensor import BlindSensor
from abbfreeathome.channels.cover_actuator import (
    AtticWindowActuator,
    AwningActuator,
    BlindActuator,
    ShutterActuator,
)
from abbfreeathome.channels.des_door_ringing_sensor import DesDoorRingingSensor
from abbfreeathome.channels.force_on_off_sensor import ForceOnOffSensor
from abbfreeathome.channels.switch_sensor import (
    DimmingSensor,
    StaircaseLightSensor,
    SwitchSensor,
)
from abbfreeathome.channels.virtual.virtual_dimming_actuator import (
    VirtualDimmingActuator,
)
from abbfreeathome.channels.virtual.virtual_room_temperature_controller import (
    VirtualRoomTemperatureController,
)
from abbfreeathome.channels.virtual.virtual_switch_actuator import VirtualSwitchActuator
from abbfreeathome.device import Device
from freezegun.api import FrozenDateTimeFactory
import pytest
from syrupy.assertion import SnapshotAssertion

from custom_components.abbfreeathome_ci.const import CONF_CREATE_SUBDEVICES, DOMAIN
from custom_components.abbfreeathome_ci.event import EVENT_DESCRIPTIONS
from homeassistant.components.event import ATTR_EVENT_TYPE, DOMAIN as EVENT_DOMAIN
from homeassistant.const import STATE_UNKNOWN, Platform
from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event

from .common import (
    MockConfigEntry,
    build_channel,
    build_device,
    setup_with_channels,
    snapshot_entities,
)

SERIAL = "ABB700000001"
COVER_INPUTS = {Pairing.AL_SET_ABSOLUTE_POSITION_BLINDS_PERCENTAGE: ""}
COVER_OUTPUTS = {Pairing.AL_CURRENT_ABSOLUTE_POSITION_BLINDS_PERCENTAGE: "100"}


@dataclass(frozen=True)
class EventCase:
    """An event description with a real channel and a SysAP report firing it.

    When the SysAP reports value on datapoint, the entity fires event_type
    with extra_data.
    """

    channel_class: type[Base]
    channel_id: str
    datapoint: str
    value: str
    event_type: str
    extra_data: Any = None
    inputs: dict[Pairing, str] = field(default_factory=dict)
    outputs: dict[Pairing, str] = field(default_factory=dict)


# Cases sharing a channel define its datapoints in their first case. Virtual
# channels and covers report requests on inputs, sensors on outputs.
EVENT_CASES = {
    "EventVirtualDimmingActuatorOnOff": EventCase(
        VirtualDimmingActuator,
        "ch0000",
        datapoint="idp0000",
        value="1",
        event_type="on",
        inputs={
            Pairing.AL_SWITCH_ON_OFF: "0",
            Pairing.AL_RELATIVE_SET_VALUE_CONTROL: "0",
            Pairing.AL_ABSOLUTE_SET_VALUE_CONTROL: "0",
        },
        outputs={
            Pairing.AL_INFO_ON_OFF: "0",
            Pairing.AL_INFO_ACTUAL_DIMMING_VALUE: "0",
        },
    ),
    "EventVirtualDimmingActuatorDimming": EventCase(
        VirtualDimmingActuator,
        "ch0000",
        datapoint="idp0001",
        value="9",
        event_type="longpress_up",
    ),
    "EventVirtualDimmingActuatorBrightness": EventCase(
        VirtualDimmingActuator,
        "ch0000",
        datapoint="idp0002",
        value="40",
        event_type="requested_brightness",
        extra_data=40.0,
    ),
    # The library uses 0 = open, Home Assistant 0 = closed. The library
    # inverts awnings, so their positions match on both sides.
    "EventAtticWindowActuatorRequestedPosition": EventCase(
        AtticWindowActuator,
        "ch0001",
        datapoint="idp0000",
        value="100",
        event_type="requested_position",
        extra_data=0,
        inputs=COVER_INPUTS,
        outputs=COVER_OUTPUTS,
    ),
    "EventAwningActuatorRequestedPosition": EventCase(
        AwningActuator,
        "ch0002",
        datapoint="idp0000",
        value="30",
        event_type="requested_position",
        extra_data=30,
        inputs=COVER_INPUTS,
        outputs=COVER_OUTPUTS,
    ),
    "EventBlindActuatorRequestedPosition": EventCase(
        BlindActuator,
        "ch0003",
        datapoint="idp0000",
        value="30",
        event_type="requested_position",
        extra_data=70,
        inputs=COVER_INPUTS,
        outputs=COVER_OUTPUTS,
    ),
    "EventShutterActuatorRequestedPosition": EventCase(
        ShutterActuator,
        "ch0004",
        datapoint="idp0000",
        value="0",
        event_type="requested_position",
        extra_data=100,
        inputs=COVER_INPUTS,
        outputs=COVER_OUTPUTS,
    ),
    "EventBlindSensorState": EventCase(
        BlindSensor,
        "ch0005",
        datapoint="odp0000",
        value="1",
        event_type="move_down",
        outputs={Pairing.AL_MOVE_UP_DOWN: "0", Pairing.AL_STOP_STEP_UP_DOWN: "0"},
    ),
    # A ring fires the standard "ring", then the legacy "activated".
    "EventDesDoorRingingSensorActivated": EventCase(
        DesDoorRingingSensor,
        "ch0006",
        datapoint="odp0000",
        value="1",
        event_type="activated",
        outputs={Pairing.AL_TIMED_START_STOP: "0"},
    ),
    "EventDimmingSensorState": EventCase(
        DimmingSensor,
        "ch0007",
        datapoint="odp0001",
        value="9",
        event_type="longpress_up",
        outputs={
            Pairing.AL_SWITCH_ON_OFF: "0",
            Pairing.AL_RELATIVE_SET_VALUE_CONTROL: "0",
        },
    ),
    "EventForceOnOffSensorOnOff": EventCase(
        ForceOnOffSensor,
        "ch0008",
        datapoint="odp0000",
        value="3",
        event_type="on",
        outputs={Pairing.AL_FORCED: "1"},
    ),
    "EventStaircaseLightSensorOnOff": EventCase(
        StaircaseLightSensor,
        "ch0009",
        datapoint="odp0000",
        value="1",
        event_type="on",
        outputs={Pairing.AL_TIMED_START_STOP: "0"},
    ),
    "EventSwitchSensorOnOff": EventCase(
        SwitchSensor,
        "ch000a",
        datapoint="odp0000",
        value="1",
        event_type="on",
        outputs={Pairing.AL_SWITCH_ON_OFF: "0"},
    ),
    "EventVirtualRoomTemperatureControllerOnOff": EventCase(
        VirtualRoomTemperatureController,
        "ch000b",
        datapoint="idp0000",
        value="1",
        event_type="On",
        inputs={
            Pairing.AL_CONTROLLER_ON_OFF_REQUEST: "0",
            Pairing.AL_ECO_ON_OFF: "0",
            Pairing.AL_INFO_ABSOLUTE_SET_POINT_REQUEST: "",
        },
        outputs={
            Pairing.AL_SET_POINT_TEMPERATURE: "21",
            Pairing.AL_CONTROLLER_ON_OFF: "1",
            Pairing.AL_STATE_INDICATION: "65",
            Pairing.AL_MEASURED_TEMPERATURE: "20",
        },
    ),
    "EventVirtualRoomTemperatureControllerEcoOnOff": EventCase(
        VirtualRoomTemperatureController,
        "ch000b",
        datapoint="idp0001",
        value="1",
        event_type="On",
    ),
    "EventVirtualRoomTemperatureControllerTargetTemperature": EventCase(
        VirtualRoomTemperatureController,
        "ch000b",
        datapoint="idp0002",
        value="22.5",
        event_type="requested_target_temperature",
        extra_data=22.5,
    ),
    "EventVirtualSwitchActuatorOnOff": EventCase(
        VirtualSwitchActuator,
        "ch000c",
        datapoint="idp0000",
        value="1",
        event_type="On",
        inputs={Pairing.AL_SWITCH_ON_OFF: "0"},
        outputs={Pairing.AL_INFO_ON_OFF: "0"},
    ),
}

VIRTUAL_DIMMER_KEYS = [
    key
    for key, case in EVENT_CASES.items()
    if case.channel_class is VirtualDimmingActuator
]

# Requests that can repeat with the same value, such as two presses on a
# virtual dimmer's button, or two identical cover position requests.
REPEATABLE_KEYS = [
    "EventVirtualDimmingActuatorOnOff",
    "EventVirtualDimmingActuatorDimming",
    "EventVirtualDimmingActuatorBrightness",
    "EventAtticWindowActuatorRequestedPosition",
    "EventAwningActuatorRequestedPosition",
    "EventBlindActuatorRequestedPosition",
    "EventShutterActuatorRequestedPosition",
]


@pytest.fixture(autouse=True)
def event_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load only the event platform."""
    monkeypatch.setattr(
        "custom_components.abbfreeathome_ci.PLATFORMS", [Platform.EVENT]
    )


def test_cases_cover_all_descriptions() -> None:
    """Test every event description has a case with its channel class."""
    assert list(EVENT_CASES) == list(EVENT_DESCRIPTIONS)
    for key, case in EVENT_CASES.items():
        assert case.channel_class is EVENT_DESCRIPTIONS[key]["channel_class"]


def _build_channels(device: Device) -> dict[str, Base]:
    """Build one real channel per event case; cases may share a channel."""
    channels: dict[str, Base] = {}
    for case in EVENT_CASES.values():
        if case.channel_id not in channels:
            channels[case.channel_id] = build_channel(
                case.channel_class,
                device,
                case.channel_id,
                inputs=case.inputs,
                outputs=case.outputs,
            )
    return channels


async def _setup_channel(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    key: str,
) -> Base:
    """Set up the real channel of an event case and return it."""
    channel = _build_channels(build_device(SERIAL))[EVENT_CASES[key].channel_id]
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    return channel


def _entity_id(entity_registry: er.EntityRegistry, key: str) -> str:
    """Return the entity ID of an event case by its unique ID."""
    entity_id = entity_registry.async_get_entity_id(
        EVENT_DOMAIN, DOMAIN, f"{SERIAL}_{EVENT_CASES[key].channel_id}_{key}"
    )
    assert entity_id is not None
    return entity_id


def _report(channel: Base, key: str, value: str | None = None) -> None:
    """Report the datapoint of an event case from the SysAP."""
    case = EVENT_CASES[key]
    channel.update_channel(
        f"{SERIAL}/{case.channel_id}/{case.datapoint}",
        case.value if value is None else value,
    )


def _track_states(hass: HomeAssistant, entity_id: str) -> list[State | None]:
    """Collect each state the entity writes from now on."""
    states: list[State | None] = []

    @callback
    def _state_changed(event: Event[EventStateChangedData]) -> None:
        states.append(event.data["new_state"])

    async_track_state_change_event(hass, entity_id, _state_changed)
    return states


def _fired(states: list[State | None]) -> list[tuple[str, Any]]:
    """Return the event type and extra data of each fired event."""
    return [
        (state.attributes[ATTR_EVENT_TYPE], state.attributes["extra_data"])
        for state in states
    ]


async def test_event_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the event entities of all descriptions."""
    channels = _build_channels(build_device(SERIAL))

    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, list(channels.values())
    )

    snapshot_entities(hass, snapshot, mock_config_entry.entry_id)


@pytest.mark.parametrize("key", EVENT_CASES)
async def test_event_fires_on_report(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    key: str,
) -> None:
    """Test an event entity fires when the SysAP reports its datapoint."""
    case = EVENT_CASES[key]
    channel = await _setup_channel(
        hass, mock_config_entry, mock_free_at_home_settings, key
    )
    entity_id = _entity_id(entity_registry, key)

    _report(channel, key)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.attributes[ATTR_EVENT_TYPE] == case.event_type
    assert state.attributes["extra_data"] == case.extra_data


async def test_event_doorbell_rings(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test a doorbell fires the standard "ring", then the legacy "activated"."""
    key = "EventDesDoorRingingSensorActivated"
    channel = await _setup_channel(
        hass, mock_config_entry, mock_free_at_home_settings, key
    )
    states = _track_states(hass, _entity_id(entity_registry, key))

    _report(channel, key)
    await hass.async_block_till_done()

    assert _fired(states) == [("ring", None), ("activated", None)]


@pytest.mark.parametrize("key", REPEATABLE_KEYS)
async def test_event_repeated_request_fires_again(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    freezer: FrozenDateTimeFactory,
    key: str,
) -> None:
    """Test a repeated request fires again, even within the same millisecond."""
    case = EVENT_CASES[key]
    channel = await _setup_channel(
        hass, mock_config_entry, mock_free_at_home_settings, key
    )
    states = _track_states(hass, _entity_id(entity_registry, key))
    # Both reports arrive in the same millisecond.
    freezer.move_to("2026-11-08T12:00:00+00:00")

    _report(channel, key)
    _report(channel, key)
    await hass.async_block_till_done()

    assert _fired(states) == [(case.event_type, case.extra_data)] * 2


@pytest.mark.parametrize(
    ("key", "value", "event_type", "extra_data"),
    [
        ("EventVirtualDimmingActuatorOnOff", "1", "on", None),
        ("EventVirtualDimmingActuatorOnOff", "0", "off", None),
        # A physical dimming sensor sends 9 or 1 for a long press up or down,
        # and 8 or 0 on release; the free@home app steps with 15 and 7.
        ("EventVirtualDimmingActuatorDimming", "9", "longpress_up", None),
        ("EventVirtualDimmingActuatorDimming", "8", "longpress_up_release", None),
        ("EventVirtualDimmingActuatorDimming", "1", "longpress_down", None),
        ("EventVirtualDimmingActuatorDimming", "0", "longpress_down_release", None),
        ("EventVirtualDimmingActuatorDimming", "15", "step_up", None),
        ("EventVirtualDimmingActuatorDimming", "7", "step_down", None),
        ("EventVirtualDimmingActuatorBrightness", "0", "requested_brightness", 0.0),
        ("EventVirtualDimmingActuatorBrightness", "42.5", "requested_brightness", 42.5),
        ("EventVirtualDimmingActuatorBrightness", "100", "requested_brightness", 100.0),
    ],
)
async def test_event_virtual_dimmer_request(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    key: str,
    value: str,
    event_type: str,
    extra_data: float | None,
) -> None:
    """Test each request to a virtual dimmer fires only the event of its input."""
    channel = await _setup_channel(
        hass, mock_config_entry, mock_free_at_home_settings, key
    )
    states = {
        dimmer_key: _track_states(hass, _entity_id(entity_registry, dimmer_key))
        for dimmer_key in VIRTUAL_DIMMER_KEYS
    }

    _report(channel, key, value)
    await hass.async_block_till_done()

    assert {dimmer_key: _fired(states[dimmer_key]) for dimmer_key in states} == {
        dimmer_key: [(event_type, extra_data)] if dimmer_key == key else []
        for dimmer_key in states
    }


async def test_event_virtual_dimmer_steps_and_stops(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test a release after a dimming step fires a stop, also when repeated."""
    key = "EventVirtualDimmingActuatorDimming"
    channel = await _setup_channel(
        hass, mock_config_entry, mock_free_at_home_settings, key
    )
    states = _track_states(hass, _entity_id(entity_registry, key))

    for value in ("15", "0", "0", "7", "0", "9", "8", "1", "0"):
        _report(channel, key, value)
    await hass.async_block_till_done()

    assert [event_type for event_type, _ in _fired(states)] == [
        "step_up",
        "stop",
        "stop",
        "step_down",
        "stop",
        "longpress_up",
        "longpress_up_release",
        "longpress_down",
        "longpress_down_release",
    ]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("EventVirtualDimmingActuatorOnOff", ""),
        ("EventVirtualDimmingActuatorOnOff", "2"),
        ("EventVirtualDimmingActuatorOnOff", "true"),
        ("EventVirtualDimmingActuatorDimming", "16"),
        ("EventVirtualDimmingActuatorDimming", "invalid"),
        ("EventVirtualDimmingActuatorBrightness", ""),
        ("EventVirtualDimmingActuatorBrightness", "invalid"),
        ("EventVirtualDimmingActuatorBrightness", "-1"),
        ("EventVirtualDimmingActuatorBrightness", "101"),
        ("EventVirtualDimmingActuatorBrightness", "nan"),
        ("EventBlindActuatorRequestedPosition", "invalid"),
    ],
)
async def test_event_ignores_unknown_request(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    key: str,
    value: str,
) -> None:
    """Test a request the library cannot decode fires no event."""
    channel = await _setup_channel(
        hass, mock_config_entry, mock_free_at_home_settings, key
    )

    _report(channel, key, value)
    await hass.async_block_till_done()

    assert hass.states.get(_entity_id(entity_registry, key)).state == STATE_UNKNOWN


async def test_event_ignores_cover_position_feedback(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test the position a cover reports fires no requested position event."""
    key = "EventBlindActuatorRequestedPosition"
    channel = await _setup_channel(
        hass, mock_config_entry, mock_free_at_home_settings, key
    )

    channel.update_channel(f"{SERIAL}/ch0003/odp0000", "50")
    await hass.async_block_till_done()

    assert hass.states.get(_entity_id(entity_registry, key)).state == STATE_UNKNOWN


async def test_event_ignores_virtual_dimmer_feedback(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test the state a virtual dimmer publishes fires no request event."""
    channel = await _setup_channel(
        hass, mock_config_entry, mock_free_at_home_settings, VIRTUAL_DIMMER_KEYS[0]
    )

    channel.update_channel(f"{SERIAL}/ch0000/odp0000", "1")
    channel.update_channel(f"{SERIAL}/ch0000/odp0001", "50")
    await hass.async_block_till_done()

    assert [
        hass.states.get(_entity_id(entity_registry, key)).state
        for key in VIRTUAL_DIMMER_KEYS
    ] == [STATE_UNKNOWN] * 3


@pytest.mark.parametrize(
    "filename", ["strings.json", "translations/en.json", "translations/de.json"]
)
def test_virtual_dimmer_event_types_are_translated(filename: str) -> None:
    """Test each event type of the virtual dimmer has a translation.

    The virtual switch and room temperature controller fire "On" and "Off",
    which their translations lack, so this checks the virtual dimmer only.
    """
    strings = json.loads(
        Path("custom_components/abbfreeathome_ci", filename).read_text(encoding="utf-8")
    )
    for key in VIRTUAL_DIMMER_KEYS:
        kwargs = EVENT_DESCRIPTIONS[key]["entity_description_kwargs"]
        translated = strings["entity"]["event"][kwargs["translation_key"]][
            "state_attributes"
        ]["event_type"]["state"]
        assert set(translated) == set(kwargs["event_types"])
        assert all(
            re.fullmatch(r"[a-z0-9]+(?:[_-][a-z0-9]+)*", event_type)
            for event_type in translated
        )


@pytest.mark.parametrize(("value", "position"), [("100", 100), ("0", 0)])
async def test_event_awning_open_close_echo(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    value: str,
    position: int,
) -> None:
    """Test the echo of opening or closing an awning fires its position.

    Opening and closing an awning set its requested position to 100 or 0,
    which the SysAP echoes back.
    """
    key = "EventAwningActuatorRequestedPosition"
    channel = await _setup_channel(
        hass, mock_config_entry, mock_free_at_home_settings, key
    )

    _report(channel, key, value)
    await hass.async_block_till_done()

    state = hass.states.get(_entity_id(entity_registry, key))
    assert state.attributes["extra_data"] == position


async def test_event_removes_callbacks_on_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test unloaded event entities no longer follow their channels."""
    channels = _build_channels(build_device(SERIAL))
    # The doorbell follows its state; three controller events share a channel.
    doorbell, controller = channels["ch0006"], channels["ch000b"]
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [doorbell, controller]
    )
    key = "EventDesDoorRingingSensorActivated"
    entity_id = _entity_id(entity_registry, key)

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)

    _report(doorbell, key)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id) == state
    assert doorbell._callbacks == {"state": set()}
    assert controller._callbacks == {
        "requested_state": set(),
        "requested_eco_mode": set(),
        "requested_target_temperature": set(),
    }


@pytest.mark.parametrize(
    ("create_subdevices", "multi_device_identifier"),
    [
        (False, (DOMAIN, SERIAL)),
        (True, (DOMAIN, f"{SERIAL}_ch000a")),
    ],
)
async def test_event_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    create_subdevices: bool,
    multi_device_identifier: tuple[str, str],
) -> None:
    """Test events of multi-channel devices belong to subdevices if enabled."""
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
    channels = _build_channels(multi_device)
    assert multi_device.is_multi_device
    single_device = build_device("ABB700000002")
    single_channel = build_channel(
        SwitchSensor, single_device, outputs={Pairing.AL_SWITCH_ON_OFF: "0"}
    )
    assert not single_device.is_multi_device

    await setup_with_channels(
        hass,
        entry,
        mock_free_at_home_settings,
        [channels["ch000a"], single_channel],
    )

    def device_identifiers(unique_id: str) -> set[tuple[str, str]]:
        """Return the identifiers of the device of an event entity."""
        entity_id = entity_registry.async_get_entity_id(EVENT_DOMAIN, DOMAIN, unique_id)
        entity_entry = entity_registry.async_get(entity_id)
        return device_registry.async_get(entity_entry.device_id).identifiers

    assert device_identifiers(f"{SERIAL}_ch000a_EventSwitchSensorOnOff") == {
        multi_device_identifier
    }
    assert device_identifiers("ABB700000002_ch0000_EventSwitchSensorOnOff") == {
        (DOMAIN, "ABB700000002")
    }
