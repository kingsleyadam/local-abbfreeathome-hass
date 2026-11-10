"""Test ABB-free@home number."""

from dataclasses import dataclass
from unittest.mock import MagicMock

from abbfreeathome.bin.pairing import Pairing
from abbfreeathome.channels.base import Base
from abbfreeathome.channels.virtual.virtual_brightness_sensor import (
    VirtualBrightnessSensor,
)
from abbfreeathome.channels.virtual.virtual_energy_battery import VirtualEnergyBattery
from abbfreeathome.channels.virtual.virtual_energy_inverter import VirtualEnergyInverter
from abbfreeathome.channels.virtual.virtual_energy_two_way_meter import (
    VirtualEnergyTwoWayMeter,
)
from abbfreeathome.channels.virtual.virtual_room_temperature_controller import (
    VirtualRoomTemperatureController,
)
from abbfreeathome.channels.virtual.virtual_temperature_sensor import (
    VirtualTemperatureSensor,
)
from abbfreeathome.channels.virtual.virtual_wind_sensor import VirtualWindSensor
from abbfreeathome.device import Device
import pytest
from syrupy.assertion import SnapshotAssertion

from custom_components.abbfreeathome_ci.const import CONF_CREATE_SUBDEVICES, DOMAIN
from custom_components.abbfreeathome_ci.number import NUMBER_DESCRIPTIONS
from homeassistant.components.homeassistant import (
    DOMAIN as HOMEASSISTANT_DOMAIN,
    SERVICE_UPDATE_ENTITY,
)
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, Platform
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


@dataclass(frozen=True)
class NumberCase:
    """A number description with a real virtual channel.

    Home Assistant feeds virtual channels: the SysAP reports a number on the
    output with the pairing, at first as reported, and setting the number to
    value sets that output to command.
    """

    channel_class: type[Base]
    channel_id: str
    pairing: Pairing
    reported: str
    value: float
    command: str


# Unique IDs must never change; each ends with the description's key, typos
# included. All values differ, so a number that shows another one fails.
NUMBER_CASES = {
    "VirtualBrightnessSensor": NumberCase(
        VirtualBrightnessSensor,
        "ch0000",
        Pairing.AL_BRIGHTNESS_LEVEL,
        "1000",
        2500,
        "2500",
    ),
    "VirtualEnergyBatteryBatteryPower": NumberCase(
        VirtualEnergyBattery, "ch0001", Pairing.AL_BATTERY_POWER, "1.5", -2.5, "-2.5"
    ),
    "VirtualEnergyBatterySoc": NumberCase(
        VirtualEnergyBattery, "ch0001", Pairing.AL_SOC, "80", 55, "55"
    ),
    "VirtualEnergyBatteryImportedToday": NumberCase(
        VirtualEnergyBattery,
        "ch0001",
        Pairing.AL_MEASURED_IMPORTED_ENERGY_TODAY,
        "110",
        115,
        "115",
    ),
    "VirtualEnergyBatteryExportedToday": NumberCase(
        VirtualEnergyBattery,
        "ch0001",
        Pairing.AL_MEASURED_EXPORTED_ENERGY_TODAY,
        "120",
        125,
        "125",
    ),
    "VirtualEnergyBatteryImportedTotal": NumberCase(
        VirtualEnergyBattery,
        "ch0001",
        Pairing.AL_MEASURED_TOTAL_ENERGY_IMPORTED,
        "130",
        135,
        "135",
    ),
    "VirtualEnergyBatteryExportedTotal": NumberCase(
        VirtualEnergyBattery,
        "ch0001",
        Pairing.AL_MEASURED_TOTAL_ENERGY_EXPORTED,
        "140",
        145,
        "145",
    ),
    "VirtualEnergyInverterCurrentPower": NumberCase(
        VirtualEnergyInverter,
        "ch0002",
        Pairing.AL_MEASURED_CURRENT_POWER_CONSUMED,
        "500.5",
        600.5,
        "600.5",
    ),
    "VirtualEnergyInverterImportedToday": NumberCase(
        VirtualEnergyInverter,
        "ch0002",
        Pairing.AL_MEASURED_IMPORTED_ENERGY_TODAY,
        "210",
        215,
        "215",
    ),
    "VirtualEnergyInverterImportedTotal": NumberCase(
        VirtualEnergyInverter,
        "ch0002",
        Pairing.AL_MEASURED_TOTAL_ENERGY_IMPORTED,
        "230",
        235,
        "235",
    ),
    "VirtualEnergyTwoWayMeterCurrentPower": NumberCase(
        VirtualEnergyTwoWayMeter,
        "ch0003",
        Pairing.AL_MEASURED_CURRENT_POWER_CONSUMED,
        "-50.5",
        -60.5,
        "-60.5",
    ),
    "VirtualEnergyTwoMayMeterImportedToday": NumberCase(
        VirtualEnergyTwoWayMeter,
        "ch0003",
        Pairing.AL_MEASURED_IMPORTED_ENERGY_TODAY,
        "310",
        315,
        "315",
    ),
    "VirtualEnergyTwoMayMeterExportedToday": NumberCase(
        VirtualEnergyTwoWayMeter,
        "ch0003",
        Pairing.AL_MEASURED_EXPORTED_ENERGY_TODAY,
        "320",
        325,
        "325",
    ),
    "VirtualEnergyTwoMayMeterImportedTotal": NumberCase(
        VirtualEnergyTwoWayMeter,
        "ch0003",
        Pairing.AL_MEASURED_TOTAL_ENERGY_IMPORTED,
        "330",
        335,
        "335",
    ),
    "VirtualEnergyTwoMayMeterExportedTotal": NumberCase(
        VirtualEnergyTwoWayMeter,
        "ch0003",
        Pairing.AL_MEASURED_TOTAL_ENERGY_EXPORTED,
        "340",
        345,
        "345",
    ),
    "VirtualRoomTemperatureControllerCurrentTemperature": NumberCase(
        VirtualRoomTemperatureController,
        "ch0004",
        Pairing.AL_MEASURED_TEMPERATURE,
        "20.5",
        19.5,
        "19.5",
    ),
    "VirtualRoomTemperatureControllerTargetTemperature": NumberCase(
        VirtualRoomTemperatureController,
        "ch0004",
        Pairing.AL_SET_POINT_TEMPERATURE,
        "21.5",
        22.5,
        "22.5",
    ),
    "VirtualTemperatureSensor": NumberCase(
        VirtualTemperatureSensor,
        "ch0005",
        Pairing.AL_OUTDOOR_TEMPERATURE,
        "-5.5",
        -7.5,
        "-7.5",
    ),
    "VirtualWindSensorForce": NumberCase(
        VirtualWindSensor, "ch0006", Pairing.AL_WIND_FORCE, "6", 8, "8"
    ),
    "VirtualWindSensorSpeed": NumberCase(
        VirtualWindSensor, "ch0006", Pairing.AL_WIND_SPEED, "12.5", 15.5, "15.5"
    ),
}


@pytest.fixture(autouse=True)
def number_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load only the number platform."""
    monkeypatch.setattr(
        "custom_components.abbfreeathome_ci.PLATFORMS", [Platform.NUMBER]
    )


def test_cases_cover_all_descriptions() -> None:
    """Test every number description has a case with its channel class."""
    assert list(NUMBER_CASES) == list(NUMBER_DESCRIPTIONS)
    for key, case in NUMBER_CASES.items():
        assert case.channel_class is NUMBER_DESCRIPTIONS[key]["channel_class"]


def _build_channels(device: Device) -> dict[str, Base]:
    """Build one real channel per channel ID with the outputs of its cases."""
    channel_classes: dict[str, type[Base]] = {}
    outputs: dict[str, dict[Pairing, str]] = {}
    for case in NUMBER_CASES.values():
        channel_classes[case.channel_id] = case.channel_class
        outputs.setdefault(case.channel_id, {})[case.pairing] = case.reported
    return {
        channel_id: build_channel(
            channel_classes[channel_id], device, channel_id, outputs=channel_outputs
        )
        for channel_id, channel_outputs in outputs.items()
    }


def _output(channel: Base, key: str) -> str:
    """Return the ID of the output a number case reports and sets its value on."""
    output_id, _value = channel.get_output_by_pairing(NUMBER_CASES[key].pairing)
    return output_id


def _entity_id(entity_registry: er.EntityRegistry, key: str) -> str:
    """Return the entity ID of a number case by its unique ID."""
    entity_id = entity_registry.async_get_entity_id(
        NUMBER_DOMAIN, DOMAIN, f"{SERIAL}_{NUMBER_CASES[key].channel_id}_{key}"
    )
    assert entity_id is not None
    return entity_id


async def test_number_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the number entities of all descriptions and their values."""
    channels = _build_channels(build_device(SERIAL))

    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, list(channels.values())
    )

    snapshot_entities(hass, snapshot, mock_config_entry.entry_id)
    for key, case in NUMBER_CASES.items():
        assert hass.states.get(_entity_id(entity_registry, key)).state == case.reported


@pytest.mark.parametrize("key", NUMBER_CASES)
async def test_number_follows_sysap(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    key: str,
) -> None:
    """Test a number shows the value the SysAP reports without a command."""
    case = NUMBER_CASES[key]
    device = build_device(SERIAL)
    channel = _build_channels(device)[case.channel_id]
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )

    channel.update_channel(
        f"{SERIAL}/{case.channel_id}/{_output(channel, key)}", case.command
    )
    await hass.async_block_till_done()

    assert hass.states.get(_entity_id(entity_registry, key)).state == case.command
    device.api.set_datapoint.assert_not_awaited()


@pytest.mark.parametrize("key", NUMBER_CASES)
async def test_number_set_value(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    key: str,
) -> None:
    """Test setting a number sets its output on the SysAP."""
    case = NUMBER_CASES[key]
    device = build_device(SERIAL)
    channel = _build_channels(device)[case.channel_id]
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: _entity_id(entity_registry, key), ATTR_VALUE: case.value},
        blocking=True,
    )

    device.api.set_datapoint.assert_awaited_once_with(
        device_serial=SERIAL,
        channel_id=case.channel_id,
        datapoint=_output(channel, key),
        value=case.command,
    )


async def test_number_skips_none_values(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test no number is created for a channel attribute without a value."""
    # Without the other outputs, the battery knows only its state of charge.
    battery = build_channel(
        VirtualEnergyBattery, build_device(SERIAL), outputs={Pairing.AL_SOC: "80"}
    )

    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [battery]
    )

    entries = er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    )
    assert [entry.unique_id for entry in entries] == [
        f"{SERIAL}_ch0000_VirtualEnergyBatterySoc"
    ]


async def test_number_update_entity(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test updating a number refreshes its value from the SysAP."""
    assert await async_setup_component(hass, HOMEASSISTANT_DOMAIN, {})
    key = "VirtualEnergyInverterImportedToday"
    device = build_device(SERIAL)
    channel = _build_channels(device)["ch0002"]
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, key)
    device.api.get_datapoint.return_value = ["999"]

    await hass.services.async_call(
        HOMEASSISTANT_DOMAIN,
        SERVICE_UPDATE_ENTITY,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    assert hass.states.get(entity_id).state == "999"
    device.api.get_datapoint.assert_any_await(
        device_serial=SERIAL, channel_id="ch0002", datapoint=_output(channel, key)
    )


async def test_number_removes_callbacks_on_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test unloaded numbers no longer follow their channel."""
    key = "VirtualEnergyInverterImportedToday"
    channel = _build_channels(build_device(SERIAL))["ch0002"]
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, key)

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)

    channel.update_channel(f"{SERIAL}/ch0002/{_output(channel, key)}", "999")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id) == state
    assert channel._callbacks == {
        "current_power": set(),
        "imported_today": set(),
        "imported_total": set(),
    }


@pytest.mark.parametrize(
    ("create_subdevices", "multi_device_identifier"),
    [
        (False, (DOMAIN, SERIAL)),
        (True, (DOMAIN, f"{SERIAL}_ch0000")),
    ],
)
async def test_number_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    create_subdevices: bool,
    multi_device_identifier: tuple[str, str],
) -> None:
    """Test a number of a multi-channel device belongs to a subdevice if enabled."""
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
        VirtualBrightnessSensor,
        single_device,
        outputs={Pairing.AL_BRIGHTNESS_LEVEL: "1000"},
    )
    assert not single_device.is_multi_device

    await setup_with_channels(
        hass, entry, mock_free_at_home_settings, [channels["ch0000"], single_channel]
    )

    def device_identifiers(unique_id: str) -> set[tuple[str, str]]:
        """Return the identifiers of the device of a number."""
        entity_id = entity_registry.async_get_entity_id(
            NUMBER_DOMAIN, DOMAIN, unique_id
        )
        entity_entry = entity_registry.async_get(entity_id)
        return device_registry.async_get(entity_entry.device_id).identifiers

    assert device_identifiers(f"{SERIAL}_ch0000_VirtualBrightnessSensor") == {
        multi_device_identifier
    }
    assert device_identifiers("ABB700000002_ch0000_VirtualBrightnessSensor") == {
        (DOMAIN, "ABB700000002")
    }
