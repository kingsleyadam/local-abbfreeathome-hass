"""Test ABB-free@home switch."""

from dataclasses import dataclass, field
from unittest.mock import MagicMock, call

from abbfreeathome.bin.pairing import Pairing
from abbfreeathome.bin.parameter import Parameter
from abbfreeathome.channels.base import Base
from abbfreeathome.channels.movement_detector import BlockableMovementDetector
from abbfreeathome.channels.switch_actuator import (
    MWireSwitchActuator,
    SwitchActuator,
    WelcomeIPMuteActuator,
)
from abbfreeathome.channels.switch_sensor import DimmingSensor, SwitchSensor
from abbfreeathome.channels.virtual.virtual_brightness_sensor import (
    VirtualBrightnessSensor,
)
from abbfreeathome.channels.virtual.virtual_rain_sensor import VirtualRainSensor
from abbfreeathome.channels.virtual.virtual_room_temperature_controller import (
    VirtualRoomTemperatureController,
)
from abbfreeathome.channels.virtual.virtual_switch_actuator import VirtualSwitchActuator
from abbfreeathome.channels.virtual.virtual_temperature_sensor import (
    VirtualTemperatureSensor,
)
from abbfreeathome.channels.virtual.virtual_wind_sensor import VirtualWindSensor
from abbfreeathome.channels.virtual.virtual_window_door_sensor import (
    VirtualWindowDoorSensor,
)
from abbfreeathome.device import Device
import pytest
from syrupy.assertion import SnapshotAssertion

from custom_components.abbfreeathome_ci.const import CONF_CREATE_SUBDEVICES, DOMAIN
from custom_components.abbfreeathome_ci.switch import (
    SWITCH_DESCRIPTIONS,
    FreeAtHomeSwitchEntity,
)
from homeassistant.components.homeassistant import (
    DOMAIN as HOMEASSISTANT_DOMAIN,
    SERVICE_UPDATE_ENTITY,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
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
LED_MODE = {Parameter.PID_LED_OPERATION_MODE: "2"}


@dataclass(frozen=True)
class SwitchCase:
    """A switch description with a real channel that is on.

    Turning the switch on and off sets command_datapoint to on and off. The
    SysAP reports the new state on state_datapoint with off_state.
    """

    channel_class: type[Base]
    channel_id: str
    unique_id_suffix: str
    command_datapoint: str
    state_datapoint: str
    inputs: dict[Pairing, str] = field(default_factory=dict)
    outputs: dict[Pairing, str] = field(default_factory=dict)
    parameters: dict[Parameter, str] = field(default_factory=dict)
    on: str = "1"
    off: str = "0"
    off_state: str = "0"


# Unique IDs must never change. Switches without a translation key keep the
# legacy "switch" suffix for backward compatibility.
SWITCH_CASES = {
    "DimmingSensorLed": SwitchCase(
        DimmingSensor,
        "ch0000",
        "DimmingSensorLed",
        command_datapoint="idp0000",
        state_datapoint="idp0000",
        inputs={Pairing.AL_INFO_ON_OFF: "1"},
        outputs={
            Pairing.AL_SWITCH_ON_OFF: "0",
            Pairing.AL_RELATIVE_SET_VALUE_CONTROL: "0",
        },
        parameters=LED_MODE,
    ),
    "SwitchActuator": SwitchCase(
        SwitchActuator,
        "ch0001",
        "switch",
        command_datapoint="idp0000",
        state_datapoint="odp0000",
        inputs={Pairing.AL_SWITCH_ON_OFF: "1", Pairing.AL_FORCED: "0"},
        outputs={Pairing.AL_INFO_ON_OFF: "1", Pairing.AL_INFO_FORCE: "0"},
    ),
    "MWireSwitchActuator": SwitchCase(
        MWireSwitchActuator,
        "ch0002",
        "switch",
        command_datapoint="idp0000",
        state_datapoint="odp0000",
        inputs={Pairing.AL_MWIRE_SWITCH_ON_OFF: "1"},
        outputs={Pairing.AL_MWIRE_SWITCH_ON_OFF: "1"},
    ),
    "SwitchSensorLed": SwitchCase(
        SwitchSensor,
        "ch0003",
        "SwitchSensorLed",
        command_datapoint="idp0000",
        state_datapoint="idp0000",
        inputs={Pairing.AL_INFO_ON_OFF: "1"},
        outputs={Pairing.AL_SWITCH_ON_OFF: "0"},
        parameters=LED_MODE,
    ),
    "VirtualBrightessSensorAlarm": SwitchCase(
        VirtualBrightnessSensor,
        "ch0004",
        "VirtualBrightessSensorAlarm",
        command_datapoint="odp0001",
        state_datapoint="odp0001",
        outputs={Pairing.AL_BRIGHTNESS_LEVEL: "100", Pairing.AL_BRIGHTNESS_ALARM: "1"},
    ),
    "VirtualRainSensorAlarm": SwitchCase(
        VirtualRainSensor,
        "ch0005",
        "VirtualRainSensorAlarm",
        command_datapoint="odp0000",
        state_datapoint="odp0000",
        outputs={Pairing.AL_RAIN_ALARM: "1"},
    ),
    # The on/off and eco switches share one virtual room temperature controller.
    "VirtualRoomTemperatureControllerOnOff": SwitchCase(
        VirtualRoomTemperatureController,
        "ch0006",
        "VirtualRoomTemperatureControllerOnOff",
        command_datapoint="odp0001",
        state_datapoint="odp0001",
        outputs={
            Pairing.AL_SET_POINT_TEMPERATURE: "21",
            Pairing.AL_CONTROLLER_ON_OFF: "1",
            Pairing.AL_STATE_INDICATION: "68",
            Pairing.AL_MEASURED_TEMPERATURE: "20",
        },
    ),
    "VirtualRoomTemperatureControllerECOOnOff": SwitchCase(
        VirtualRoomTemperatureController,
        "ch0006",
        "VirtualRoomTemperatureControllerECOOnOff",
        command_datapoint="odp0002",
        state_datapoint="odp0002",
        on="68",
        off="65",
        off_state="65",
    ),
    "VirtualSwitchActuatorOnOff": SwitchCase(
        VirtualSwitchActuator,
        "ch0007",
        "switch",
        command_datapoint="odp0000",
        state_datapoint="odp0000",
        outputs={Pairing.AL_INFO_ON_OFF: "1"},
    ),
    "VirtualWindSensorAlarm": SwitchCase(
        VirtualWindSensor,
        "ch0008",
        "VirtualWindSensorAlarm",
        command_datapoint="odp0001",
        state_datapoint="odp0001",
        outputs={
            Pairing.AL_WIND_SPEED: "5",
            Pairing.AL_WIND_ALARM: "1",
            Pairing.AL_WIND_FORCE: "3",
        },
    ),
    "VirtualWindowDoorSensorOnOff": SwitchCase(
        VirtualWindowDoorSensor,
        "ch0009",
        "switch",
        command_datapoint="odp0000",
        state_datapoint="odp0000",
        outputs={Pairing.AL_WINDOW_DOOR: "1"},
    ),
    "VirtualTemperatureSensorAlarm": SwitchCase(
        VirtualTemperatureSensor,
        "ch000a",
        "VirtualTemperatureSensorAlarm",
        command_datapoint="odp0001",
        state_datapoint="odp0001",
        outputs={Pairing.AL_OUTDOOR_TEMPERATURE: "5", Pairing.AL_FROST_ALARM: "1"},
    ),
    "WelcomeIPMuteActuator": SwitchCase(
        WelcomeIPMuteActuator,
        "ch000b",
        "WelcomeIPMuteActuator",
        command_datapoint="idp0000",
        state_datapoint="odp0000",
        inputs={Pairing.AL_SWITCH_ON_OFF: "1"},
        outputs={Pairing.AL_INFO_ON_OFF: "1"},
    ),
    "BlockableMovementDetector": SwitchCase(
        BlockableMovementDetector,
        "ch000c",
        "BlockableMovementDetector",
        command_datapoint="idp0000",
        state_datapoint="odp0002",
        inputs={Pairing.AL_LOCK_SENSOR: "1"},
        outputs={
            Pairing.AL_TIMED_MOVEMENT: "0",
            Pairing.AL_BRIGHTNESS_LEVEL: "100",
            Pairing.AL_INFO_LOCKED_SENSOR: "1",
        },
    ),
}


@pytest.fixture(autouse=True)
def switch_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load only the switch platform."""
    monkeypatch.setattr(
        "custom_components.abbfreeathome_ci.PLATFORMS", [Platform.SWITCH]
    )


def test_cases_cover_all_descriptions() -> None:
    """Test every switch description has a case with its channel class."""
    assert list(SWITCH_CASES) == list(SWITCH_DESCRIPTIONS)
    for key, case in SWITCH_CASES.items():
        assert case.channel_class is SWITCH_DESCRIPTIONS[key]["channel_class"]


def _build_channels(device: Device) -> dict[str, Base]:
    """Build one real channel per switch case; cases may share a channel."""
    channels: dict[str, Base] = {}
    for case in SWITCH_CASES.values():
        if case.channel_id not in channels:
            channels[case.channel_id] = build_channel(
                case.channel_class,
                device,
                case.channel_id,
                inputs=case.inputs,
                outputs=case.outputs,
                parameters=case.parameters,
            )
    return channels


def _entity_id(entity_registry: er.EntityRegistry, key: str) -> str:
    """Return the entity ID of a switch case by its unique ID."""
    case = SWITCH_CASES[key]
    entity_id = entity_registry.async_get_entity_id(
        SWITCH_DOMAIN,
        DOMAIN,
        f"{SERIAL}_{case.channel_id}_{case.unique_id_suffix}",
    )
    assert entity_id is not None
    return entity_id


async def test_switch_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the switch entities of all descriptions and their states."""
    device = build_device(SERIAL)
    channels = _build_channels(device)

    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, list(channels.values())
    )

    snapshot_entities(hass, snapshot, mock_config_entry.entry_id)
    for key in SWITCH_CASES:
        assert hass.states.get(_entity_id(entity_registry, key)).state == STATE_ON


@pytest.mark.parametrize("key", SWITCH_CASES)
async def test_switch_turn_off_on(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    key: str,
) -> None:
    """Test turning a switch off and on sets the datapoint and follows the SysAP."""
    case = SWITCH_CASES[key]
    device = build_device(SERIAL)
    channel = _build_channels(device)[case.channel_id]
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, key)

    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    channel.update_channel(
        f"{SERIAL}/{case.channel_id}/{case.state_datapoint}", case.off_state
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_OFF

    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )

    datapoint = {
        "device_serial": SERIAL,
        "channel_id": case.channel_id,
        "datapoint": case.command_datapoint,
    }
    assert device.api.set_datapoint.await_args_list == [
        call(**datapoint, value=case.off),
        call(**datapoint, value=case.on),
    ]


async def test_switch_skips_none_values(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test no switch is created for a channel attribute without a value."""
    device = build_device(SERIAL)
    # Without the state indication output, the eco mode is unknown.
    controller = build_channel(
        VirtualRoomTemperatureController,
        device,
        outputs={Pairing.AL_CONTROLLER_ON_OFF: "1"},
    )
    # Without the LED operation mode parameter, the LED state is unknown.
    sensor = build_channel(
        SwitchSensor, device, "ch0001", inputs={Pairing.AL_INFO_ON_OFF: "1"}
    )

    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [controller, sensor]
    )

    entries = er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    )
    assert [entry.unique_id for entry in entries] == [
        f"{SERIAL}_ch0000_VirtualRoomTemperatureControllerOnOff"
    ]


async def test_switch_update_entity(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test updating a switch refreshes its state from the SysAP."""
    assert await async_setup_component(hass, HOMEASSISTANT_DOMAIN, {})
    device = build_device(SERIAL)
    channel = _build_channels(device)["ch0001"]
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, "SwitchActuator")
    device.api.get_datapoint.return_value = ["0"]

    await hass.services.async_call(
        HOMEASSISTANT_DOMAIN,
        SERVICE_UPDATE_ENTITY,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    assert hass.states.get(entity_id).state == STATE_OFF
    device.api.get_datapoint.assert_any_await(
        device_serial=SERIAL, channel_id="ch0001", datapoint="odp0000"
    )


async def test_switch_removes_callback_on_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test an unloaded switch no longer follows its channel."""
    device = build_device(SERIAL)
    channel = _build_channels(device)["ch0001"]
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, "SwitchActuator")

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)

    channel.update_channel(f"{SERIAL}/ch0001/odp0000", "0")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id) == state
    assert not channel._callbacks["state"]


@pytest.mark.parametrize(
    ("create_subdevices", "multi_device_identifier"),
    [
        (False, (DOMAIN, SERIAL)),
        (True, (DOMAIN, f"{SERIAL}_ch0001")),
    ],
)
async def test_switch_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    create_subdevices: bool,
    multi_device_identifier: tuple[str, str],
) -> None:
    """Test a switch of a multi-channel device belongs to a subdevice if enabled."""
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
        SwitchActuator,
        single_device,
        inputs={Pairing.AL_SWITCH_ON_OFF: "1"},
        outputs={Pairing.AL_INFO_ON_OFF: "1"},
    )
    assert not single_device.is_multi_device

    await setup_with_channels(
        hass,
        entry,
        mock_free_at_home_settings,
        [channels["ch0001"], single_channel],
    )

    def device_identifiers(unique_id: str) -> set[tuple[str, str]]:
        """Return the identifiers of the device of a switch."""
        entity_id = entity_registry.async_get_entity_id(
            SWITCH_DOMAIN, DOMAIN, unique_id
        )
        entity_entry = entity_registry.async_get(entity_id)
        return device_registry.async_get(entity_entry.device_id).identifiers

    assert device_identifiers(f"{SERIAL}_ch0001_switch") == {multi_device_identifier}
    assert device_identifiers("ABB700000002_ch0000_switch") == {
        (DOMAIN, "ABB700000002")
    }


def test_switch_translation_key_fallback() -> None:
    """Test translation_key falls back to _attr_translation_key.

    Every switch has an entity description, so Home Assistant cannot reach the
    fallback.
    """
    channel = build_channel(
        SwitchActuator,
        build_device(SERIAL),
        inputs={Pairing.AL_SWITCH_ON_OFF: "1"},
        outputs={Pairing.AL_INFO_ON_OFF: "1"},
    )
    entity = FreeAtHomeSwitchEntity(
        channel,
        value_attribute="state",
        entity_description_kwargs={"key": "SwitchActuator"},
        sysap_serial_number="TEST123456",
        create_subdevices=False,
    )
    entity._attr_translation_key = "custom_translation"

    # The entity description takes precedence over _attr_translation_key.
    assert entity.translation_key is None

    del entity.entity_description
    assert entity.translation_key == "custom_translation"
