"""Test ABB-free@home select."""

from dataclasses import dataclass
import json
from pathlib import Path
from unittest.mock import MagicMock, call

from abbfreeathome.bin.pairing import Pairing
from abbfreeathome.channels.base import Base
from abbfreeathome.channels.cover_actuator import (
    AtticWindowActuator,
    AwningActuator,
    BlindActuator,
    ShutterActuator,
)
from abbfreeathome.channels.dimming_actuator import DimmingActuator
from abbfreeathome.channels.switch_actuator import SwitchActuator
from abbfreeathome.device import Device
import pytest
from syrupy.assertion import SnapshotAssertion

from custom_components.abbfreeathome_ci.const import CONF_CREATE_SUBDEVICES, DOMAIN
from custom_components.abbfreeathome_ci.select import SELECT_DESCRIPTIONS
from homeassistant.components.select import (
    ATTR_OPTION,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNKNOWN, Platform
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
STRINGS_PATH = Path("custom_components/abbfreeathome_ci/strings.json")
# Selecting an option sets the forced input (idp0000); the SysAP reports the
# forced position on AL_INFO_FORCE (odp0000).
FORCED_INPUT = "idp0000"
FORCED_OUTPUT = "odp0000"
# Cover actuators set and report a forced position with the same values.
COVER_FORCED_POSITIONS = {"deactivated": "0", "forced_open": "2", "forced_closed": "3"}
# Switch and dimming actuators report forcing on and off with other values than
# they set.
ON_OFF_COMMANDS = {"deactivated": "0", "forced_on": "3", "forced_off": "2"}
ON_OFF_REPORTS = {"deactivated": "0", "forced_on": "4", "forced_off": "5"}


@dataclass(frozen=True)
class SelectCase:
    """A select description with a real channel.

    Selecting an option sets the forced input to its value in commands; the
    SysAP reports the option with its value in reports.
    """

    channel_class: type[Base]
    channel_id: str
    forced_input: Pairing
    commands: dict[str, str]
    reports: dict[str, str]


# Unique IDs must never change; each ends with the description's key.
SELECT_CASES = {
    "AtticWindowActuatorForcedPosition": SelectCase(
        AtticWindowActuator,
        "ch0000",
        Pairing.AL_FORCED_UP_DOWN,
        COVER_FORCED_POSITIONS,
        COVER_FORCED_POSITIONS,
    ),
    "AwningActuatorForcedPosition": SelectCase(
        AwningActuator,
        "ch0001",
        Pairing.AL_FORCED_UP_DOWN,
        COVER_FORCED_POSITIONS,
        COVER_FORCED_POSITIONS,
    ),
    "BlindActuatorForcedPosition": SelectCase(
        BlindActuator,
        "ch0002",
        Pairing.AL_FORCED_UP_DOWN,
        COVER_FORCED_POSITIONS,
        COVER_FORCED_POSITIONS,
    ),
    "ShutterActuatorForcedPosition": SelectCase(
        ShutterActuator,
        "ch0003",
        Pairing.AL_FORCED_UP_DOWN,
        COVER_FORCED_POSITIONS,
        COVER_FORCED_POSITIONS,
    ),
    "SwitchActuatorForcedPosition": SelectCase(
        SwitchActuator, "ch0004", Pairing.AL_FORCED, ON_OFF_COMMANDS, ON_OFF_REPORTS
    ),
    "DimmingActuatorForcedPosition": SelectCase(
        DimmingActuator, "ch0005", Pairing.AL_FORCED, ON_OFF_COMMANDS, ON_OFF_REPORTS
    ),
}


@pytest.fixture(autouse=True)
def select_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load only the select platform."""
    monkeypatch.setattr(
        "custom_components.abbfreeathome_ci.PLATFORMS", [Platform.SELECT]
    )


def test_cases_cover_all_descriptions() -> None:
    """Test every select description has a case with its channel class."""
    assert list(SELECT_CASES) == list(SELECT_DESCRIPTIONS)
    for key, case in SELECT_CASES.items():
        assert case.channel_class is SELECT_DESCRIPTIONS[key]["channel_class"]


@pytest.mark.parametrize("key", SELECT_DESCRIPTIONS)
def test_select_options_are_translated(key: str) -> None:
    """Test every option has a translated state and unknown is no option.

    The library reports "unknown" while no forced position is known. It must
    not be selectable, so Home Assistant shows the entity state as unknown.
    """
    entity_description_kwargs = SELECT_DESCRIPTIONS[key]["entity_description_kwargs"]
    strings = json.loads(STRINGS_PATH.read_text(encoding="utf-8"))
    translation = strings["entity"]["select"][
        entity_description_kwargs["translation_key"]
    ]

    assert "unknown" not in entity_description_kwargs["options"]
    assert set(entity_description_kwargs["options"]) == set(translation["state"])


def _build_channel(device: Device, key: str, forced: str = "0") -> Base:
    """Build the real channel of a select case; 0 means no position is forced."""
    case = SELECT_CASES[key]
    return build_channel(
        case.channel_class,
        device,
        case.channel_id,
        inputs={case.forced_input: "0"},
        outputs={Pairing.AL_INFO_FORCE: forced},
    )


def _entity_id(entity_registry: er.EntityRegistry, key: str) -> str:
    """Return the entity ID of a select case by its unique ID."""
    entity_id = entity_registry.async_get_entity_id(
        SELECT_DOMAIN, DOMAIN, f"{SERIAL}_{SELECT_CASES[key].channel_id}_{key}"
    )
    assert entity_id is not None
    return entity_id


async def test_select_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the select entities of all descriptions, with no position forced."""
    device = build_device(SERIAL)

    await setup_with_channels(
        hass,
        mock_config_entry,
        mock_free_at_home_settings,
        [_build_channel(device, key) for key in SELECT_CASES],
    )

    snapshot_entities(hass, snapshot, mock_config_entry.entry_id)
    for key in SELECT_CASES:
        assert hass.states.get(_entity_id(entity_registry, key)).state == "deactivated"


@pytest.mark.parametrize("key", SELECT_CASES)
async def test_select_follows_sysap(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    key: str,
) -> None:
    """Test a select shows the forced position the SysAP reports.

    An empty value is no forced position the library knows, so the select is
    unknown.
    """
    case = SELECT_CASES[key]
    device = build_device(SERIAL)
    channel = _build_channel(device, key, forced="")
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, key)
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    for option, value in [*case.reports.items(), (STATE_UNKNOWN, "")]:
        channel.update_channel(f"{SERIAL}/{case.channel_id}/{FORCED_OUTPUT}", value)
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == option
    device.api.set_datapoint.assert_not_awaited()


@pytest.mark.parametrize("key", SELECT_CASES)
async def test_select_option(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    key: str,
) -> None:
    """Test selecting each option sets the forced input on the SysAP."""
    case = SELECT_CASES[key]
    device = build_device(SERIAL)
    await setup_with_channels(
        hass,
        mock_config_entry,
        mock_free_at_home_settings,
        [_build_channel(device, key)],
    )
    entity_id = _entity_id(entity_registry, key)

    for option in case.commands:
        await hass.services.async_call(
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {ATTR_ENTITY_ID: entity_id, ATTR_OPTION: option},
            blocking=True,
        )

    assert device.api.set_datapoint.await_args_list == [
        call(
            device_serial=SERIAL,
            channel_id=case.channel_id,
            datapoint=FORCED_INPUT,
            value=value,
        )
        for value in case.commands.values()
    ]


async def test_select_removes_callback_on_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test an unloaded select no longer follows its channel."""
    key = "SwitchActuatorForcedPosition"
    channel = _build_channel(build_device(SERIAL), key)
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, key)

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)

    channel.update_channel(f"{SERIAL}/ch0004/{FORCED_OUTPUT}", "4")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id) == state
    assert channel._callbacks == {"forced_position": set()}


@pytest.mark.parametrize(
    ("create_subdevices", "multi_device_identifier"),
    [
        (False, (DOMAIN, SERIAL)),
        (True, (DOMAIN, f"{SERIAL}_ch0004")),
    ],
)
async def test_select_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    create_subdevices: bool,
    multi_device_identifier: tuple[str, str],
) -> None:
    """Test a select of a multi-channel device belongs to a subdevice if enabled."""
    key = "SwitchActuatorForcedPosition"
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
    multi_channel = _build_channel(multi_device, key)
    _build_channel(multi_device, "DimmingActuatorForcedPosition")
    assert multi_device.is_multi_device
    single_device = build_device("ABB700000002")
    single_channel = _build_channel(single_device, key)
    assert not single_device.is_multi_device

    await setup_with_channels(
        hass, entry, mock_free_at_home_settings, [multi_channel, single_channel]
    )

    def device_identifiers(unique_id: str) -> set[tuple[str, str]]:
        """Return the identifiers of the device of a select."""
        entity_id = entity_registry.async_get_entity_id(
            SELECT_DOMAIN, DOMAIN, unique_id
        )
        entity_entry = entity_registry.async_get(entity_id)
        return device_registry.async_get(entity_entry.device_id).identifiers

    assert device_identifiers(f"{SERIAL}_ch0004_{key}") == {multi_device_identifier}
    assert device_identifiers(f"ABB700000002_ch0004_{key}") == {
        (DOMAIN, "ABB700000002")
    }
