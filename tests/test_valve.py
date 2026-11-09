"""Test ABB-free@home valve."""

from collections.abc import Generator
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from abbfreeathome.bin.pairing import Pairing
from abbfreeathome.channels.base import Base
from abbfreeathome.channels.valve_actuator import (
    CoolingActuator,
    HeatingActuator,
    HeatingCoolingActuator,
)
from abbfreeathome.device import Device
import pytest
from syrupy.assertion import SnapshotAssertion

from custom_components.abbfreeathome_ci.const import CONF_CREATE_SUBDEVICES, DOMAIN
from custom_components.abbfreeathome_ci.valve import VALVE_DESCRIPTIONS
from homeassistant.components.homeassistant import (
    DOMAIN as HOMEASSISTANT_DOMAIN,
    SERVICE_UPDATE_ENTITY,
)
from homeassistant.components.valve import (
    ATTR_CURRENT_POSITION,
    ATTR_POSITION,
    DOMAIN as VALVE_DOMAIN,
    ValveState,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_SET_VALVE_POSITION,
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
# The SysAP reports heating valves at 30 and cooling valves at 60 of 100.
HEATING_INPUTS = {Pairing.AL_ACTUATING_VALUE_HEATING: "0"}
HEATING_OUTPUTS = {Pairing.AL_INFO_VALUE_HEATING: "30"}
COOLING_INPUTS = {Pairing.AL_ACTUATING_VALUE_COOLING: "0"}
COOLING_OUTPUTS = {Pairing.AL_INFO_VALUE_COOLING: "60"}


@dataclass(frozen=True)
class ValveCase:
    """A valve description with a real channel.

    Setting the position sets position_input; the SysAP reports the position
    on position_output, at first as position.
    """

    channel_class: type[Base]
    channel_id: str
    unique_id_suffix: str
    position_input: str
    position_output: str
    position: int
    inputs: dict[Pairing, str]
    outputs: dict[Pairing, str]


# Unique IDs must never change. The heating actuator's valve keeps the legacy
# suffix "valve".
VALVE_CASES = {
    "HeatingActuatorValve": ValveCase(
        HeatingActuator,
        "ch0000",
        "valve",
        position_input="idp0000",
        position_output="odp0000",
        position=30,
        inputs=HEATING_INPUTS,
        outputs=HEATING_OUTPUTS,
    ),
    "CoolingActuatorValve": ValveCase(
        CoolingActuator,
        "ch0001",
        "CoolingActuatorValve",
        position_input="idp0000",
        position_output="odp0000",
        position=60,
        inputs=COOLING_INPUTS,
        outputs=COOLING_OUTPUTS,
    ),
    # The heating and cooling valves share one heating/cooling actuator.
    "HeatingCoolingActuatorHeatingValve": ValveCase(
        HeatingCoolingActuator,
        "ch0002",
        "HeatingCoolingActuatorHeatingValve",
        position_input="idp0000",
        position_output="odp0000",
        position=30,
        inputs=HEATING_INPUTS | COOLING_INPUTS,
        outputs=HEATING_OUTPUTS | COOLING_OUTPUTS,
    ),
    "HeatingCoolingActuatorCoolingValve": ValveCase(
        HeatingCoolingActuator,
        "ch0002",
        "HeatingCoolingActuatorCoolingValve",
        position_input="idp0001",
        position_output="odp0001",
        position=60,
        inputs=HEATING_INPUTS | COOLING_INPUTS,
        outputs=HEATING_OUTPUTS | COOLING_OUTPUTS,
    ),
}


@pytest.fixture(autouse=True)
def valve_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load only the valve platform."""
    monkeypatch.setattr(
        "custom_components.abbfreeathome_ci.PLATFORMS", [Platform.VALVE]
    )


# compat: homeassistant<2026.11 - pytest-homeassistant provides entity_registry_enabled_by_default
@pytest.fixture
def entity_registry_enabled_by_default() -> Generator[None]:
    """Enable all entities in the registry, as the fixture of pytest-homeassistant."""
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        return_value=True,
    ):
        yield


def test_cases_cover_all_descriptions() -> None:
    """Test every valve description has a case with its channel class."""
    assert list(VALVE_CASES) == list(VALVE_DESCRIPTIONS)
    for key, case in VALVE_CASES.items():
        assert case.channel_class is VALVE_DESCRIPTIONS[key]["channel_class"]


def _build_channels(device: Device) -> dict[str, Base]:
    """Build one real channel per valve case; cases may share a channel."""
    channels: dict[str, Base] = {}
    for case in VALVE_CASES.values():
        if case.channel_id not in channels:
            channels[case.channel_id] = build_channel(
                case.channel_class,
                device,
                case.channel_id,
                inputs=case.inputs,
                outputs=case.outputs,
            )
    return channels


def _entity_id(entity_registry: er.EntityRegistry, key: str) -> str:
    """Return the entity ID of a valve case by its unique ID."""
    case = VALVE_CASES[key]
    entity_id = entity_registry.async_get_entity_id(
        VALVE_DOMAIN, DOMAIN, f"{SERIAL}_{case.channel_id}_{case.unique_id_suffix}"
    )
    assert entity_id is not None
    return entity_id


async def test_valves_disabled_by_default(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test valves are disabled by default."""
    channels = _build_channels(build_device(SERIAL))

    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, list(channels.values())
    )

    for key in VALVE_CASES:
        entity_id = _entity_id(entity_registry, key)
        entity_entry = entity_registry.async_get(entity_id)
        assert entity_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert hass.states.get(entity_id) is None


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_valve_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the valve entities of all descriptions once enabled."""
    channels = _build_channels(build_device(SERIAL))

    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, list(channels.values())
    )

    snapshot_entities(hass, snapshot, mock_config_entry.entry_id)
    for key, case in VALVE_CASES.items():
        state = hass.states.get(_entity_id(entity_registry, key))
        assert state.state == ValveState.OPEN
        assert state.attributes[ATTR_CURRENT_POSITION] == case.position


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
@pytest.mark.parametrize("key", VALVE_CASES)
async def test_valve_follows_sysap(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    key: str,
) -> None:
    """Test a valve shows the position the SysAP reports.

    A value that is no number leaves the position unknown.
    """
    case = VALVE_CASES[key]
    device = build_device(SERIAL)
    channel = _build_channels(device)[case.channel_id]
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, key)

    for value, expected, position in (
        ("0", ValveState.CLOSED, 0),
        ("100", ValveState.OPEN, 100),
        ("", STATE_UNKNOWN, None),
    ):
        channel.update_channel(
            f"{SERIAL}/{case.channel_id}/{case.position_output}", value
        )
        await hass.async_block_till_done()
        state = hass.states.get(entity_id)
        assert state.state == expected
        assert state.attributes[ATTR_CURRENT_POSITION] == position
    device.api.set_datapoint.assert_not_awaited()


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
@pytest.mark.parametrize("key", VALVE_CASES)
async def test_valve_set_position(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    key: str,
) -> None:
    """Test setting a valve's position sets its input on the SysAP."""
    case = VALVE_CASES[key]
    device = build_device(SERIAL)
    await setup_with_channels(
        hass,
        mock_config_entry,
        mock_free_at_home_settings,
        [_build_channels(device)[case.channel_id]],
    )

    await hass.services.async_call(
        VALVE_DOMAIN,
        SERVICE_SET_VALVE_POSITION,
        {ATTR_ENTITY_ID: _entity_id(entity_registry, key), ATTR_POSITION: 40},
        blocking=True,
    )

    device.api.set_datapoint.assert_awaited_once_with(
        device_serial=SERIAL,
        channel_id=case.channel_id,
        datapoint=case.position_input,
        value="40",
    )


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_valve_update_entity(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test updating a valve refreshes its position from the SysAP."""
    assert await async_setup_component(hass, HOMEASSISTANT_DOMAIN, {})
    device = build_device(SERIAL)
    await setup_with_channels(
        hass,
        mock_config_entry,
        mock_free_at_home_settings,
        [_build_channels(device)["ch0000"]],
    )
    entity_id = _entity_id(entity_registry, "HeatingActuatorValve")
    device.api.get_datapoint.return_value = ["70"]

    await hass.services.async_call(
        HOMEASSISTANT_DOMAIN,
        SERVICE_UPDATE_ENTITY,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    assert hass.states.get(entity_id).attributes[ATTR_CURRENT_POSITION] == 70
    device.api.get_datapoint.assert_awaited_once_with(
        device_serial=SERIAL, channel_id="ch0000", datapoint="odp0000"
    )


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_valve_removes_callbacks_on_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test unloaded valves no longer follow their channels."""
    channels = _build_channels(build_device(SERIAL))
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, list(channels.values())
    )
    entity_ids = [_entity_id(entity_registry, key) for key in VALVE_CASES]

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    states = [hass.states.get(entity_id) for entity_id in entity_ids]

    for case in VALVE_CASES.values():
        channels[case.channel_id].update_channel(
            f"{SERIAL}/{case.channel_id}/{case.position_output}", "0"
        )
    await hass.async_block_till_done()
    assert [hass.states.get(entity_id) for entity_id in entity_ids] == states
    assert channels["ch0000"]._callbacks == {"position": set()}
    assert channels["ch0001"]._callbacks == {"position": set()}
    assert channels["ch0002"]._callbacks == {
        "heating_position": set(),
        "cooling_position": set(),
    }


@pytest.mark.parametrize(
    ("create_subdevices", "multi_device_identifier"),
    [
        (False, (DOMAIN, SERIAL)),
        (True, (DOMAIN, f"{SERIAL}_ch0000")),
    ],
)
async def test_valve_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    create_subdevices: bool,
    multi_device_identifier: tuple[str, str],
) -> None:
    """Test a valve of a multi-channel device belongs to a subdevice if enabled."""
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
        HeatingActuator, single_device, inputs=HEATING_INPUTS, outputs=HEATING_OUTPUTS
    )
    assert not single_device.is_multi_device

    await setup_with_channels(
        hass, entry, mock_free_at_home_settings, [channels["ch0000"], single_channel]
    )

    def device_identifiers(unique_id: str) -> set[tuple[str, str]]:
        """Return the identifiers of the device of a valve."""
        entity_id = entity_registry.async_get_entity_id(VALVE_DOMAIN, DOMAIN, unique_id)
        entity_entry = entity_registry.async_get(entity_id)
        return device_registry.async_get(entity_entry.device_id).identifiers

    # Valves are disabled by default, but still belong to their device.
    assert device_identifiers(f"{SERIAL}_ch0000_valve") == {multi_device_identifier}
    assert device_identifiers("ABB700000002_ch0000_valve") == {(DOMAIN, "ABB700000002")}
