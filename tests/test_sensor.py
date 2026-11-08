"""Test ABB-free@home sensor."""

import asyncio
from dataclasses import dataclass, field
import logging
from runpy import run_path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from abbfreeathome import DevicesChangedEvent
from abbfreeathome.bin.pairing import Pairing
from abbfreeathome.bin.parameter import Parameter
from abbfreeathome.channels.air_quality_sensor import AirQualitySensor
from abbfreeathome.channels.base import Base
from abbfreeathome.channels.brightness_sensor import BrightnessSensor
from abbfreeathome.channels.heating_cooling_sensor import HeatingCoolingSensor
from abbfreeathome.channels.movement_detector import (
    BlockableMovementDetector,
    MovementDetector,
)
from abbfreeathome.channels.temperature_sensor import TemperatureSensor
from abbfreeathome.channels.wind_sensor import WindSensor
from abbfreeathome.channels.window_door_sensor import WindowDoorSensor
from abbfreeathome.device import Device
from abbfreeathome.exceptions import ClientConnectionError
import pytest
from syrupy.assertion import SnapshotAssertion

from custom_components.abbfreeathome_ci import sensor as sensor_platform
from custom_components.abbfreeathome_ci.const import CONF_CREATE_SUBDEVICES, DOMAIN
from custom_components.abbfreeathome_ci.entity import FreeAtHomeEntity
from custom_components.abbfreeathome_ci.sensor import SENSOR_DESCRIPTIONS
from homeassistant import const
from homeassistant.components.homeassistant import (
    DOMAIN as HOMEASSISTANT_DOMAIN,
    SERVICE_UPDATE_ENTITY,
)
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

from .common import (
    MockConfigEntry,
    build_channel,
    build_device,
    devices_changed,
    setup_with_channels,
    snapshot_entities,
)

SERIAL = "ABB700000001"
PARAMETERS_UNIQUE_ID = f"{SERIAL}_parameters"
SWITCH_OFF_TIME = Parameter.PID_AUTONOMOUS_SWITCH_OFF_TIME_DURATION


@dataclass(frozen=True)
class SensorCase:
    """A sensor description with a real channel.

    When the SysAP reports value on datapoint, Home Assistant shows state.
    """

    channel_class: type[Base]
    channel_id: str
    datapoint: str
    value: str
    state: str
    outputs: dict[Pairing, str] = field(default_factory=dict)


# Cases sharing a channel define its datapoints in their first case.
SENSOR_CASES = {
    "AirQualitySensorCO2": SensorCase(
        AirQualitySensor,
        "ch0000",
        datapoint="odp0000",
        value="1200",
        state="1200.0",
        outputs={
            Pairing.AL_INFO_CO_2: "800",
            Pairing.AL_CO2_ALERT: "0",
            Pairing.AL_INFO_VOC_INDEX: "100",
            Pairing.AL_VOC_ALERT: "0",
            Pairing.AL_HUMIDITY: "45",
        },
    ),
    "AirQualitySensorVOC": SensorCase(
        AirQualitySensor, "ch0000", datapoint="odp0002", value="150", state="150"
    ),
    "AirQualitySensorHumidity": SensorCase(
        AirQualitySensor, "ch0000", datapoint="odp0004", value="50", state="50"
    ),
    "BrightnessSensor": SensorCase(
        BrightnessSensor,
        "ch0001",
        datapoint="odp0000",
        value="250",
        state="250.0",
        outputs={Pairing.AL_BRIGHTNESS_LEVEL: "100", Pairing.AL_BRIGHTNESS_ALARM: "0"},
    ),
    "HeatingCoolingSensor": SensorCase(
        HeatingCoolingSensor,
        "ch0002",
        datapoint="odp0000",
        value="1",
        state="cooling",
        outputs={Pairing.AL_HEATING_COOLING: "0"},
    ),
    "MovementDetectorBrightness": SensorCase(
        MovementDetector,
        "ch0003",
        datapoint="odp0001",
        value="50",
        state="50.0",
        outputs={Pairing.AL_TIMED_MOVEMENT: "0", Pairing.AL_BRIGHTNESS_LEVEL: "100"},
    ),
    "BlockableMovementDetectorBrightness": SensorCase(
        BlockableMovementDetector,
        "ch0004",
        datapoint="odp0001",
        value="50",
        state="50.0",
        outputs={
            Pairing.AL_TIMED_MOVEMENT: "0",
            Pairing.AL_BRIGHTNESS_LEVEL: "100",
            Pairing.AL_INFO_LOCKED_SENSOR: "0",
        },
    ),
    "WindowDoorSensorPosition": SensorCase(
        WindowDoorSensor,
        "ch0005",
        datapoint="odp0001",
        value="33",
        state="tilted",
        outputs={Pairing.AL_WINDOW_DOOR: "1", Pairing.AL_WINDOW_DOOR_POSITION: "100"},
    ),
    "TemperatureSensor": SensorCase(
        TemperatureSensor,
        "ch0006",
        datapoint="odp0000",
        value="-2.5",
        state="-2.5",
        outputs={Pairing.AL_OUTDOOR_TEMPERATURE: "5", Pairing.AL_FROST_ALARM: "0"},
    ),
    # Home Assistant's metric unit system shows wind speeds in km/h.
    "WindSensorSpeed": SensorCase(
        WindSensor,
        "ch0007",
        datapoint="odp0000",
        value="15",
        state="54.0",
        outputs={
            Pairing.AL_WIND_SPEED: "5",
            Pairing.AL_WIND_ALARM: "0",
            Pairing.AL_WIND_FORCE: "3",
        },
    ),
    "WindSensorForce": SensorCase(
        WindSensor, "ch0007", datapoint="odp0002", value="7", state="7"
    ),
}


@pytest.fixture(autouse=True)
def sensor_platform_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load only the sensor platform."""
    monkeypatch.setattr(
        "custom_components.abbfreeathome_ci.PLATFORMS", [Platform.SENSOR]
    )


def test_cases_cover_all_descriptions() -> None:
    """Test every sensor description has a case with its channel class."""
    assert list(SENSOR_CASES) == list(SENSOR_DESCRIPTIONS)
    for key, case in SENSOR_CASES.items():
        assert case.channel_class is SENSOR_DESCRIPTIONS[key]["channel_class"]


def _build_channels(device: Device) -> dict[str, Base]:
    """Build one real channel per sensor case; cases may share a channel."""
    channels: dict[str, Base] = {}
    for case in SENSOR_CASES.values():
        if case.channel_id not in channels:
            channels[case.channel_id] = build_channel(
                case.channel_class, device, case.channel_id, outputs=case.outputs
            )
    return channels


def _parameter_device() -> tuple[Device, list[Base]]:
    """Build a device with parameters on itself and two of its three channels.

    One channel parameter is unknown to the library.
    """
    device = build_device(SERIAL, parameters={"par0001": "0"})
    channels = [
        build_channel(
            Base,
            device,
            "ch0000",
            channel_name="Ceiling light",
            parameters={SWITCH_OFF_TIME: "130"},
        ),
        build_channel(
            Base,
            device,
            "ch0001",
            channel_name="Wall light",
            parameters={SWITCH_OFF_TIME: "60"},
        ),
        build_channel(Base, device, "ch0002", channel_name="Spare channel"),
    ]
    channels[1].update_parameter("parffff", "unknown value")
    return device, channels


def _with_subdevices(
    entry: MockConfigEntry, create_subdevices: bool = True
) -> MockConfigEntry:
    """Return a copy of the config entry with create_subdevices set."""
    return MockConfigEntry(
        version=entry.version,
        minor_version=entry.minor_version,
        domain=DOMAIN,
        title=entry.title,
        data={**entry.data, CONF_CREATE_SUBDEVICES: create_subdevices},
        source=entry.source,
        unique_id=entry.unique_id,
    )


def _entity_id(entity_registry: er.EntityRegistry, unique_id: str) -> str:
    """Return the entity ID of a sensor by its unique ID."""
    entity_id = entity_registry.async_get_entity_id(SENSOR_DOMAIN, DOMAIN, unique_id)
    assert entity_id is not None
    return entity_id


def _unique_ids(
    entity_registry: er.EntityRegistry, entry: MockConfigEntry
) -> list[str]:
    """Return the sorted unique IDs of a config entry's entities."""
    return sorted(
        entity_entry.unique_id
        for entity_entry in er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        )
    )


def _device_identifiers(hass: HomeAssistant, unique_id: str) -> set[tuple[str, str]]:
    """Return the identifiers of the device of a sensor."""
    entity_registry = er.async_get(hass)
    entity_entry = entity_registry.async_get(_entity_id(entity_registry, unique_id))
    return dr.async_get(hass).async_get(entity_entry.device_id).identifiers


async def test_sensor_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the sensor entities of all descriptions."""
    channels = _build_channels(build_device(SERIAL))

    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, list(channels.values())
    )

    snapshot_entities(hass, snapshot, mock_config_entry.entry_id)


@pytest.mark.parametrize("key", SENSOR_CASES)
async def test_sensor_follows_sysap(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    key: str,
) -> None:
    """Test a sensor shows the value the SysAP reports."""
    case = SENSOR_CASES[key]
    channel = _build_channels(build_device(SERIAL))[case.channel_id]
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, f"{SERIAL}_{case.channel_id}_{key}")

    channel.update_channel(f"{SERIAL}/{case.channel_id}/{case.datapoint}", case.value)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == case.state


async def test_sensor_unknown_value(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test a sensor is unknown when the SysAP reports a value it cannot read."""
    channel = _build_channels(build_device(SERIAL))["ch0006"]
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, f"{SERIAL}_ch0006_TemperatureSensor")

    channel.update_channel(f"{SERIAL}/ch0006/odp0000", "")
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_UNKNOWN


async def test_sensor_skips_none_values(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test no sensor is created for a channel attribute without a value."""
    device = build_device(SERIAL)
    # Without the VOC and humidity outputs, only the CO2 value is known.
    air_quality = build_channel(
        AirQualitySensor, device, outputs={Pairing.AL_INFO_CO_2: "800"}
    )
    # Without the force output, only the wind speed is known.
    wind = build_channel(
        WindSensor, device, "ch0001", outputs={Pairing.AL_WIND_SPEED: "5"}
    )

    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [air_quality, wind]
    )

    assert _unique_ids(entity_registry, mock_config_entry) == [
        f"{SERIAL}_ch0000_AirQualitySensorCO2",
        f"{SERIAL}_ch0001_WindSensorSpeed",
    ]


async def test_sensor_removes_callbacks_on_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test unloaded sensors no longer follow their channel."""
    channel = _build_channels(build_device(SERIAL))["ch0000"]
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, f"{SERIAL}_ch0000_AirQualitySensorCO2")

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)

    channel.update_channel(f"{SERIAL}/ch0000/odp0000", "1200")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id) == state
    assert channel._callbacks == {"co2": set(), "voc_index": set(), "humidity": set()}


# The library refreshes whether a window is open, but not its position.
@pytest.mark.parametrize(
    "key", [key for key in SENSOR_CASES if key != "WindowDoorSensorPosition"]
)
async def test_sensor_update_entity(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    key: str,
) -> None:
    """Test updating a sensor refreshes its value from the SysAP."""
    assert await async_setup_component(hass, HOMEASSISTANT_DOMAIN, {})
    case = SENSOR_CASES[key]
    device = build_device(SERIAL)
    channel = _build_channels(device)[case.channel_id]
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, f"{SERIAL}_{case.channel_id}_{key}")
    sysap = {
        datapoint_id: datapoint["value"]
        for datapoint_id, datapoint in channel._outputs.items()
    } | {case.datapoint: case.value}
    device.api.get_datapoint.side_effect = lambda **kwargs: [sysap[kwargs["datapoint"]]]

    await hass.services.async_call(
        HOMEASSISTANT_DOMAIN,
        SERVICE_UPDATE_ENTITY,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    assert hass.states.get(entity_id).state == case.state
    device.api.get_datapoint.assert_any_await(
        device_serial=SERIAL, channel_id=case.channel_id, datapoint=case.datapoint
    )


@pytest.mark.parametrize(
    ("outputs", "side_effect"),
    [
        pytest.param(
            SENSOR_CASES["WindSensorSpeed"].outputs,
            ClientConnectionError("http://sysap"),
            id="sysap_unreachable",
        ),
        # The library also reads the wind alarm when it refreshes the channel.
        pytest.param(
            {Pairing.AL_WIND_SPEED: "5", Pairing.AL_WIND_FORCE: "3"},
            None,
            id="missing_datapoint",
        ),
    ],
)
async def test_sensor_update_entity_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    caplog: pytest.LogCaptureFixture,
    outputs: dict[Pairing, str],
    side_effect: Exception | None,
) -> None:
    """Test a failed refresh logs one warning without a traceback."""
    assert await async_setup_component(hass, HOMEASSISTANT_DOMAIN, {})
    device = build_device(SERIAL)
    channel = build_channel(WindSensor, device, outputs=outputs)
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, f"{SERIAL}_ch0000_WindSensorSpeed")
    device.api.get_datapoint.return_value = ["5"]
    device.api.get_datapoint.side_effect = side_effect
    caplog.clear()

    await hass.services.async_call(
        HOMEASSISTANT_DOMAIN,
        SERVICE_UPDATE_ENTITY,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    assert hass.states.get(entity_id).state == "18.0"
    warnings = [
        record for record in caplog.records if record.levelno >= logging.WARNING
    ]
    assert [(record.levelno, record.exc_info) for record in warnings] == [
        (logging.WARNING, None)
    ]
    prefix = f"Could not refresh {entity_id} from the SysAP: "
    assert warnings[0].getMessage().startswith(prefix)


@pytest.mark.parametrize(
    ("create_subdevices", "multi_device_identifier"),
    [
        (False, (DOMAIN, SERIAL)),
        (True, (DOMAIN, f"{SERIAL}_ch0006")),
    ],
)
async def test_sensor_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    create_subdevices: bool,
    multi_device_identifier: tuple[str, str],
) -> None:
    """Test sensors of multi-channel devices belong to subdevices if enabled."""
    entry = _with_subdevices(mock_config_entry, create_subdevices)
    # A device without a room and with several channels is a multi-device.
    multi_device = build_device(SERIAL)
    channels = _build_channels(multi_device)
    assert multi_device.is_multi_device
    single_device = build_device("ABB700000002")
    single_channel = build_channel(
        TemperatureSensor,
        single_device,
        outputs={Pairing.AL_OUTDOOR_TEMPERATURE: "5"},
    )
    assert not single_device.is_multi_device

    await setup_with_channels(
        hass,
        entry,
        mock_free_at_home_settings,
        [channels["ch0006"], single_channel],
    )

    assert _device_identifiers(hass, f"{SERIAL}_ch0006_TemperatureSensor") == {
        multi_device_identifier
    }
    assert _device_identifiers(hass, "ABB700000002_ch0000_TemperatureSensor") == {
        (DOMAIN, "ABB700000002")
    }


async def test_parameter_sensor_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    snapshot: SnapshotAssertion,
) -> None:
    """Test a device's parameter sensor next to its measurement sensor."""
    device, channels = _parameter_device()
    temperature = build_channel(
        TemperatureSensor,
        device,
        "ch0003",
        outputs={Pairing.AL_OUTDOOR_TEMPERATURE: "21", Pairing.AL_FROST_ALARM: "0"},
    )

    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [*channels, temperature]
    )

    snapshot_entities(hass, snapshot, mock_config_entry.entry_id)


async def test_parameter_sensor_follows_parameters(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test the parameter sensor shows each parameter change.

    Each change is checked on its own, so that a later write cannot hide a
    missing subscription. Earlier states keep their attributes, and
    parameters unknown to the library keep their ID.
    """
    device, channels = _parameter_device()
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, channels
    )
    entity_id = _entity_id(entity_registry, PARAMETERS_UNIQUE_ID)
    old_state = hass.states.get(entity_id)

    async def report(source: Device | Base, parameter: str | Parameter, value: str):
        """Change a parameter and return the state the sensor publishes."""
        source.update_parameter(parameter, value)
        await hass.async_block_till_done()
        return hass.states.get(entity_id)

    state = await report(device, "par0001", "1")
    assert state.attributes["device_parameters"] == {"PID_LED_DAY_BRIGHTNESS": "1"}

    state = await report(device, "parfffe", "raw value")
    assert state.state == "5"
    assert state.attributes["device_parameters"] == {
        "PID_LED_DAY_BRIGHTNESS": "1",
        "parfffe": "raw value",
    }

    state = await report(channels[0], SWITCH_OFF_TIME, "140")
    assert state.attributes["channel_parameters"]["ch0000"]["parameters"] == {
        "PID_AUTONOMOUS_SWITCH_OFF_TIME_DURATION": "140"
    }

    state = await report(channels[1], "parffff", "new value")
    assert state.attributes["channel_parameters"]["ch0001"]["parameters"] == {
        "PID_AUTONOMOUS_SWITCH_OFF_TIME_DURATION": "60",
        "parffff": "new value",
    }

    # The sensor also follows a channel that had no parameters.
    state = await report(channels[2], SWITCH_OFF_TIME, "30")
    assert state.state == "6"
    assert state.attributes["channel_parameters"]["ch0002"] == {
        "name": "Spare channel",
        "parameters": {"PID_AUTONOMOUS_SWITCH_OFF_TIME_DURATION": "30"},
    }

    assert old_state.state == "4"
    assert old_state.attributes["device_parameters"] == {"PID_LED_DAY_BRIGHTNESS": "0"}
    assert old_state.attributes["channel_parameters"]["ch0000"]["parameters"] == {
        "PID_AUTONOMOUS_SWITCH_OFF_TIME_DURATION": "130"
    }


async def test_parameter_sensor_removes_callbacks_on_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test an unloaded parameter sensor no longer follows parameter changes."""
    device, channels = _parameter_device()
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, channels
    )
    entity_id = _entity_id(entity_registry, PARAMETERS_UNIQUE_ID)

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)

    device.update_parameter("par0001", "1")
    channels[0].update_parameter(SWITCH_OFF_TIME, "140")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id) == state
    for source in (device, *channels):
        assert not source._get_parameter_callbacks()


@pytest.mark.parametrize("has_device_parameters", [False, True])
async def test_parameter_sensors_of_subdevices(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    has_device_parameters: bool,
) -> None:
    """Test each channel sub-device with parameters gets its own sensor.

    The parent device keeps a sensor for its own parameters, if it has any.
    """
    entry = _with_subdevices(mock_config_entry)
    device, channels = _parameter_device()
    if not has_device_parameters:
        device.parameters.clear()

    await setup_with_channels(hass, entry, mock_free_at_home_settings, channels)

    assert _unique_ids(entity_registry, entry) == [
        f"{SERIAL}_ch0000_parameters",
        f"{SERIAL}_ch0001_parameters",
        *([PARAMETERS_UNIQUE_ID] if has_device_parameters else []),
    ]
    child_id = _entity_id(entity_registry, f"{SERIAL}_ch0000_parameters")
    assert _device_identifiers(hass, f"{SERIAL}_ch0000_parameters") == {
        (DOMAIN, f"{SERIAL}_ch0000")
    }
    assert hass.states.get(child_id).state == "1"

    device.update_parameter("par0001", "1")
    channels[0].update_parameter(SWITCH_OFF_TIME, "140")
    await hass.async_block_till_done()

    child = hass.states.get(child_id)
    assert "device_parameters" not in child.attributes
    assert child.attributes["channel_parameters"] == {
        "ch0000": {
            "name": "Ceiling light",
            "parameters": {"PID_AUTONOMOUS_SWITCH_OFF_TIME_DURATION": "140"},
        }
    }
    if has_device_parameters:
        assert _device_identifiers(hass, PARAMETERS_UNIQUE_ID) == {(DOMAIN, SERIAL)}
        parent = hass.states.get(_entity_id(entity_registry, PARAMETERS_UNIQUE_ID))
        assert parent.state == "1"
        assert parent.attributes["device_parameters"] == {"PID_LED_DAY_BRIGHTNESS": "1"}
        assert "channel_parameters" not in parent.attributes


@pytest.mark.parametrize(
    ("visible", "device_parameters", "channel_parameters", "unique_ids"),
    [
        (False, {"par0001": "0"}, {SWITCH_OFF_TIME: "130"}, []),
        (True, {}, {}, []),
        (True, {"par0001": "0"}, {}, [PARAMETERS_UNIQUE_ID]),
        (True, {}, {SWITCH_OFF_TIME: "130"}, [PARAMETERS_UNIQUE_ID]),
    ],
    ids=["no_visible_channels", "no_parameters", "device", "channel"],
)
async def test_parameter_sensor_needs_parameters(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    visible: bool,
    device_parameters: dict[str, str],
    channel_parameters: dict[Parameter, str],
    unique_ids: list[str],
) -> None:
    """Test only a device with visible channels and parameters gets a sensor."""
    device = build_device(SERIAL, parameters=device_parameters)
    channel = build_channel(Base, device, parameters=channel_parameters)

    await setup_with_channels(
        hass,
        mock_config_entry,
        mock_free_at_home_settings,
        [channel] if visible else [],
        devices=[device],
    )

    assert _unique_ids(entity_registry, mock_config_entry) == unique_ids


@pytest.mark.parametrize("create_subdevices", [False, True])
async def test_parameter_sensors_of_combined_actuator(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    create_subdevices: bool,
) -> None:
    """Test the parameter counts of a reported combined actuator.

    It has six contact and eight actuator channels with parameters, and two
    more channels that are not visible.
    """
    entry = _with_subdevices(mock_config_entry, create_subdevices)
    device = build_device(SERIAL, parameters={"par0026": "1"})
    channels = [
        build_channel(
            Base,
            device,
            f"ch{index:04x}",
            parameters={Parameter.PID_BI_CONTACT_TYPE: "2"}
            if index < 6
            else {
                Parameter.PID_DELAY_TIME: "60",
                Parameter.PID_SWITCH_ACTUATOR_BEHAVIOR_ON_MALFUNCTION: "1",
            },
        )
        for index in range(16)
    ]
    visible = [channel for index, channel in enumerate(channels) if index not in (6, 7)]

    await setup_with_channels(hass, entry, mock_free_at_home_settings, visible)

    states = {
        entity_entry.unique_id: hass.states.get(entity_entry.entity_id).state
        for entity_entry in er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        )
    }
    if create_subdevices:
        assert states == {
            PARAMETERS_UNIQUE_ID: "1",
            **{f"{SERIAL}_{c.channel_id}_parameters": "1" for c in visible[:6]},
            **{f"{SERIAL}_{c.channel_id}_parameters": "2" for c in visible[6:]},
        }
    else:
        assert states == {PARAMETERS_UNIQUE_ID: "23"}


async def test_parameter_sensor_follows_runtime_channels(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test a device added at runtime gets a parameter sensor that grows with it."""
    _, (first, second, _) = _parameter_device()
    mock_fah = await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, []
    )

    mock_fah.channels.append(first)
    # A repeated notification for the same channel changes nothing.
    for _ in range(2):
        devices_changed(mock_fah, DevicesChangedEvent(added_channels=(first,)))
        await hass.async_block_till_done()
    entity_id = _entity_id(entity_registry, PARAMETERS_UNIQUE_ID)
    assert list(hass.states.get(entity_id).attributes["channel_parameters"]) == [
        "ch0000"
    ]

    mock_fah.channels.append(second)
    devices_changed(mock_fah, DevicesChangedEvent(added_channels=(second,)))
    await hass.async_block_till_done()
    second.update_parameter(SWITCH_OFF_TIME, "70")
    await hass.async_block_till_done()

    channel_parameters = hass.states.get(entity_id).attributes["channel_parameters"]
    assert list(channel_parameters) == ["ch0000", "ch0001"]
    assert channel_parameters["ch0001"]["parameters"] == {
        "PID_AUTONOMOUS_SWITCH_OFF_TIME_DURATION": "70",
        "parffff": "unknown value",
    }


async def test_parameter_sensor_extended_while_being_added(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test a channel placed while the parameter sensor is being added."""
    _, (first, second, _) = _parameter_device()
    mock_fah = await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, []
    )
    release = asyncio.Event()
    added_to_hass = FreeAtHomeEntity.async_added_to_hass

    async def _delayed_added_to_hass(entity: FreeAtHomeEntity) -> None:
        await release.wait()
        await added_to_hass(entity)

    with patch.object(FreeAtHomeEntity, "async_added_to_hass", _delayed_added_to_hass):
        for channel in (first, second):
            mock_fah.channels.append(channel)
            devices_changed(mock_fah, DevicesChangedEvent(added_channels=(channel,)))
        release.set()
        await hass.async_block_till_done()

    # Once added, the sensor follows the channel placed in the meantime.
    second.update_parameter(SWITCH_OFF_TIME, "70")
    await hass.async_block_till_done()

    entity_id = _entity_id(entity_registry, PARAMETERS_UNIQUE_ID)
    channel_parameters = hass.states.get(entity_id).attributes["channel_parameters"]
    assert channel_parameters["ch0001"]["parameters"] == {
        "PID_AUTONOMOUS_SWITCH_OFF_TIME_DURATION": "70",
        "parffff": "unknown value",
    }


# compat: homeassistant<2026.7 - UnitOfRatio replaced CONCENTRATION_PARTS_PER_MILLION
@pytest.mark.parametrize("modern_units", [False, True])
def test_parts_per_million_compatibility(monkeypatch, modern_units):
    """Use the modern unit when available, otherwise use the legacy constant."""
    monkeypatch.setattr(
        const, "CONCENTRATION_PARTS_PER_MILLION", "legacy_ppm", raising=False
    )
    if modern_units:
        monkeypatch.setattr(
            const,
            "UnitOfRatio",
            SimpleNamespace(PARTS_PER_MILLION="modern_ppm"),
            raising=False,
        )
    else:
        monkeypatch.delattr(const, "UnitOfRatio", raising=False)

    sensor = run_path(
        sensor_platform.__file__, run_name="custom_components.abbfreeathome_ci.sensor"
    )
    expected_unit = "modern_ppm" if modern_units else "legacy_ppm"

    assert sensor["PARTS_PER_MILLION"] == expected_unit
    assert (
        sensor["SENSOR_DESCRIPTIONS"]["AirQualitySensorCO2"][
            "entity_description_kwargs"
        ]["native_unit_of_measurement"]
        == expected_unit
    )
