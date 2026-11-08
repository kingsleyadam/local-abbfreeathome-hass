"""Test ABB-free@home binary sensor."""

from dataclasses import dataclass, field
from unittest.mock import MagicMock

from abbfreeathome.bin.pairing import Pairing
from abbfreeathome.channels.air_quality_sensor import AirQualitySensor
from abbfreeathome.channels.base import Base
from abbfreeathome.channels.brightness_sensor import BrightnessSensor
from abbfreeathome.channels.carbon_monoxide_sensor import CarbonMonoxideSensor
from abbfreeathome.channels.movement_detector import (
    BlockableMovementDetector,
    MovementDetector,
)
from abbfreeathome.channels.rain_sensor import RainSensor
from abbfreeathome.channels.smoke_detector import SmokeDetector
from abbfreeathome.channels.temperature_sensor import TemperatureSensor
from abbfreeathome.channels.wind_sensor import WindSensor
from abbfreeathome.channels.window_door_sensor import WindowDoorSensor
from abbfreeathome.device import Device
import pytest
from syrupy.assertion import SnapshotAssertion

from custom_components.abbfreeathome_ci.binary_sensor import (
    SENSOR_DESCRIPTIONS,
    FreeAtHomeBinarySensorEntity,
)
from custom_components.abbfreeathome_ci.const import CONF_CREATE_SUBDEVICES, DOMAIN
from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .common import (
    MockConfigEntry,
    build_channel,
    build_device,
    setup_with_channels,
    snapshot_entities,
)

SERIAL = "ABB700000001"


@dataclass(frozen=True)
class BinarySensorCase:
    """A binary sensor description with a real channel that is on.

    The SysAP reports the state on state_datapoint, "1" for on and "0" for off.
    """

    channel_class: type[Base]
    channel_id: str
    state_datapoint: str
    outputs: dict[Pairing, str] = field(default_factory=dict)


BINARY_SENSOR_CASES = {
    # The CO2 and VOC alerts share one air quality sensor.
    "AirQualitySensorCO2Alert": BinarySensorCase(
        AirQualitySensor,
        "ch0000",
        state_datapoint="odp0001",
        outputs={
            Pairing.AL_INFO_CO_2: "800",
            Pairing.AL_CO2_ALERT: "1",
            Pairing.AL_INFO_VOC_INDEX: "100",
            Pairing.AL_VOC_ALERT: "1",
            Pairing.AL_HUMIDITY: "45",
        },
    ),
    "AirQualitySensorVOCAlert": BinarySensorCase(
        AirQualitySensor, "ch0000", state_datapoint="odp0003"
    ),
    "CarbonMonoxideSensorOnOff": BinarySensorCase(
        CarbonMonoxideSensor,
        "ch0001",
        state_datapoint="odp0000",
        outputs={Pairing.AL_CO_ALARM_ACTIVE: "1"},
    ),
    "MovementDetectorMotion": BinarySensorCase(
        MovementDetector,
        "ch0002",
        state_datapoint="odp0000",
        outputs={Pairing.AL_TIMED_MOVEMENT: "1", Pairing.AL_BRIGHTNESS_LEVEL: "100"},
    ),
    "BlockableMovementDetectorMotion": BinarySensorCase(
        BlockableMovementDetector,
        "ch0003",
        state_datapoint="odp0000",
        outputs={
            Pairing.AL_TIMED_MOVEMENT: "1",
            Pairing.AL_BRIGHTNESS_LEVEL: "100",
            Pairing.AL_INFO_LOCKED_SENSOR: "0",
        },
    ),
    "SmokeDetectorOnOff": BinarySensorCase(
        SmokeDetector,
        "ch0004",
        state_datapoint="odp0000",
        outputs={Pairing.AL_FIRE_ALARM_ACTIVE: "1"},
    ),
    "WindowDoorSensorOnOff": BinarySensorCase(
        WindowDoorSensor,
        "ch0005",
        state_datapoint="odp0000",
        outputs={Pairing.AL_WINDOW_DOOR: "1"},
    ),
    "RainSensorOnOff": BinarySensorCase(
        RainSensor,
        "ch0006",
        state_datapoint="odp0000",
        outputs={Pairing.AL_RAIN_ALARM: "1"},
    ),
    "BrightnessSensorOnOff": BinarySensorCase(
        BrightnessSensor,
        "ch0007",
        state_datapoint="odp0001",
        outputs={Pairing.AL_BRIGHTNESS_LEVEL: "100", Pairing.AL_BRIGHTNESS_ALARM: "1"},
    ),
    "TemperatureSensorOnOff": BinarySensorCase(
        TemperatureSensor,
        "ch0008",
        state_datapoint="odp0001",
        outputs={Pairing.AL_OUTDOOR_TEMPERATURE: "-2", Pairing.AL_FROST_ALARM: "1"},
    ),
    "WindSensorOnOff": BinarySensorCase(
        WindSensor,
        "ch0009",
        state_datapoint="odp0001",
        outputs={
            Pairing.AL_WIND_SPEED: "15",
            Pairing.AL_WIND_ALARM: "1",
            Pairing.AL_WIND_FORCE: "7",
        },
    ),
}


@pytest.fixture(autouse=True)
def binary_sensor_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load only the binary sensor platform."""
    monkeypatch.setattr(
        "custom_components.abbfreeathome_ci.PLATFORMS", [Platform.BINARY_SENSOR]
    )


def test_cases_cover_all_descriptions() -> None:
    """Test every binary sensor description has a case with its channel class."""
    assert list(BINARY_SENSOR_CASES) == list(SENSOR_DESCRIPTIONS)
    for key, case in BINARY_SENSOR_CASES.items():
        assert case.channel_class is SENSOR_DESCRIPTIONS[key]["channel_class"]


def _build_channels(device: Device) -> dict[str, Base]:
    """Build one real channel per binary sensor case; cases may share a channel."""
    channels: dict[str, Base] = {}
    for case in BINARY_SENSOR_CASES.values():
        if case.channel_id not in channels:
            channels[case.channel_id] = build_channel(
                case.channel_class, device, case.channel_id, outputs=case.outputs
            )
    return channels


def _entity_id(entity_registry: er.EntityRegistry, key: str) -> str:
    """Return the entity ID of a binary sensor case by its unique ID."""
    entity_id = entity_registry.async_get_entity_id(
        BINARY_SENSOR_DOMAIN,
        DOMAIN,
        f"{SERIAL}_{BINARY_SENSOR_CASES[key].channel_id}_{key}",
    )
    assert entity_id is not None
    return entity_id


async def test_binary_sensor_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the binary sensor entities of all descriptions and their states."""
    device = build_device(SERIAL)
    channels = _build_channels(device)

    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, list(channels.values())
    )

    snapshot_entities(hass, snapshot, mock_config_entry.entry_id)
    for key in BINARY_SENSOR_CASES:
        assert hass.states.get(_entity_id(entity_registry, key)).state == STATE_ON


@pytest.mark.parametrize("key", BINARY_SENSOR_CASES)
async def test_binary_sensor_follows_sysap(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    key: str,
) -> None:
    """Test a binary sensor shows the state the SysAP reports."""
    case = BINARY_SENSOR_CASES[key]
    device = build_device(SERIAL)
    channel = _build_channels(device)[case.channel_id]
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, key)
    datapoint_key = f"{SERIAL}/{case.channel_id}/{case.state_datapoint}"

    channel.update_channel(datapoint_key, "0")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_OFF

    channel.update_channel(datapoint_key, "1")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_ON


async def test_binary_sensor_skips_none_values(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test no binary sensor is created for a channel attribute without a value."""
    device = build_device(SERIAL)
    # Without the VOC alert output, the VOC alert is unknown.
    air_quality = build_channel(
        AirQualitySensor, device, outputs={Pairing.AL_CO2_ALERT: "1"}
    )
    # Without the window door output, whether the window is open is unknown.
    window = build_channel(
        WindowDoorSensor,
        device,
        "ch0001",
        outputs={Pairing.AL_WINDOW_DOOR_POSITION: "100"},
    )

    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [air_quality, window]
    )

    entries = er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    )
    assert [entry.unique_id for entry in entries] == [
        f"{SERIAL}_ch0000_AirQualitySensorCO2Alert"
    ]


async def test_binary_sensor_removes_callbacks_on_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test unloaded binary sensors no longer follow their channel."""
    device = build_device(SERIAL)
    channel = _build_channels(device)["ch0000"]
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, "AirQualitySensorCO2Alert")

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)

    channel.update_channel(f"{SERIAL}/ch0000/odp0001", "0")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id) == state
    assert channel._callbacks == {"co2_alert": set(), "voc_alert": set()}


@pytest.mark.parametrize(
    ("create_subdevices", "multi_device_identifier"),
    [
        (False, (DOMAIN, SERIAL)),
        (True, (DOMAIN, f"{SERIAL}_ch0005")),
    ],
)
async def test_binary_sensor_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    create_subdevices: bool,
    multi_device_identifier: tuple[str, str],
) -> None:
    """Test binary sensors of multi-channel devices belong to subdevices if enabled."""
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
        WindowDoorSensor, single_device, outputs={Pairing.AL_WINDOW_DOOR: "1"}
    )
    assert not single_device.is_multi_device

    await setup_with_channels(
        hass,
        entry,
        mock_free_at_home_settings,
        [channels["ch0005"], single_channel],
    )

    def device_identifiers(unique_id: str) -> set[tuple[str, str]]:
        """Return the identifiers of the device of a binary sensor."""
        entity_id = entity_registry.async_get_entity_id(
            BINARY_SENSOR_DOMAIN, DOMAIN, unique_id
        )
        entity_entry = entity_registry.async_get(entity_id)
        return device_registry.async_get(entity_entry.device_id).identifiers

    assert device_identifiers(f"{SERIAL}_ch0005_WindowDoorSensorOnOff") == {
        multi_device_identifier
    }
    assert device_identifiers("ABB700000002_ch0000_WindowDoorSensorOnOff") == {
        (DOMAIN, "ABB700000002")
    }


def test_binary_sensor_translation_key_fallback() -> None:
    """Test translation_key falls back to _attr_translation_key.

    Every binary sensor has an entity description, so Home Assistant cannot
    reach the fallback.
    """
    channel = build_channel(
        WindowDoorSensor, build_device(SERIAL), outputs={Pairing.AL_WINDOW_DOOR: "1"}
    )
    entity = FreeAtHomeBinarySensorEntity(
        channel,
        value_attribute="state",
        entity_description_kwargs={
            "key": "WindowDoorSensorOnOff",
            "translation_key": "window_door",
        },
        sysap_serial_number="TEST123456",
        create_subdevices=False,
    )
    entity._attr_translation_key = "custom_translation"

    # The entity description takes precedence over _attr_translation_key.
    assert entity.translation_key == "window_door"

    del entity.entity_description
    assert entity.translation_key == "custom_translation"
