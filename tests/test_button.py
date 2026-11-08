"""Test ABB-free@home button."""

from dataclasses import dataclass
from unittest.mock import MagicMock

from abbfreeathome.bin.pairing import Pairing
from abbfreeathome.channels.trigger import Trigger
from abbfreeathome.channels.virtual.virtual_trigger import VirtualTrigger
from abbfreeathome.device import Device
from freezegun.api import FrozenDateTimeFactory
import pytest
from syrupy.assertion import SnapshotAssertion

from custom_components.abbfreeathome_ci.button import BUTTON_DESCRIPTIONS
from custom_components.abbfreeathome_ci.const import CONF_CREATE_SUBDEVICES, DOMAIN
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID, Platform
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
# Pressing a trigger sets its AL_TIMED_START_STOP input to 1.
TRIGGER_INPUTS = {Pairing.AL_TIMED_START_STOP: "0"}


@dataclass(frozen=True)
class ButtonCase:
    """A button description with a real trigger channel."""

    channel_class: type[Trigger]
    channel_id: str


# Unique IDs must never change; every button has the suffix "button".
BUTTON_CASES = {
    "Trigger": ButtonCase(Trigger, "ch0000"),
    "VirtualTrigger": ButtonCase(VirtualTrigger, "ch0001"),
}


@pytest.fixture(autouse=True)
def button_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load only the button platform."""
    monkeypatch.setattr(
        "custom_components.abbfreeathome_ci.PLATFORMS", [Platform.BUTTON]
    )


def test_cases_cover_all_descriptions() -> None:
    """Test every button description has a case with its channel class."""
    assert list(BUTTON_CASES) == list(BUTTON_DESCRIPTIONS)
    for key, case in BUTTON_CASES.items():
        assert case.channel_class is BUTTON_DESCRIPTIONS[key]["channel_class"]


def _build_channels(device: Device) -> dict[str, Trigger]:
    """Build one real trigger channel per button case."""
    return {
        key: build_channel(
            case.channel_class, device, case.channel_id, inputs=TRIGGER_INPUTS
        )
        for key, case in BUTTON_CASES.items()
    }


def _entity_id(entity_registry: er.EntityRegistry, key: str) -> str:
    """Return the entity ID of a button case by its unique ID."""
    entity_id = entity_registry.async_get_entity_id(
        BUTTON_DOMAIN, DOMAIN, f"{SERIAL}_{BUTTON_CASES[key].channel_id}_button"
    )
    assert entity_id is not None
    return entity_id


async def test_button_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the button entities of all descriptions."""
    device = build_device(SERIAL)
    channels = _build_channels(device)

    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, list(channels.values())
    )

    snapshot_entities(hass, snapshot, mock_config_entry.entry_id)


@pytest.mark.parametrize("key", BUTTON_CASES)
async def test_button_press(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    freezer: FrozenDateTimeFactory,
    key: str,
) -> None:
    """Test pressing a button starts its trigger on the SysAP."""
    case = BUTTON_CASES[key]
    device = build_device(SERIAL)
    channel = _build_channels(device)[key]
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, key)
    freezer.move_to("2026-11-08T12:00:00+00:00")

    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )

    device.api.set_datapoint.assert_awaited_once_with(
        device_serial=SERIAL,
        channel_id=case.channel_id,
        datapoint="idp0000",
        value="1",
    )
    # Home Assistant shows when a button was last pressed.
    assert hass.states.get(entity_id).state == "2026-11-08T12:00:00+00:00"


@pytest.mark.parametrize(
    ("create_subdevices", "multi_device_identifier"),
    [
        (False, (DOMAIN, SERIAL)),
        (True, (DOMAIN, f"{SERIAL}_ch0000")),
    ],
)
async def test_button_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    create_subdevices: bool,
    multi_device_identifier: tuple[str, str],
) -> None:
    """Test a button of a multi-channel device belongs to a subdevice if enabled."""
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
    single_channel = build_channel(Trigger, single_device, inputs=TRIGGER_INPUTS)
    assert not single_device.is_multi_device

    await setup_with_channels(
        hass,
        entry,
        mock_free_at_home_settings,
        [channels["Trigger"], single_channel],
    )

    def device_identifiers(unique_id: str) -> set[tuple[str, str]]:
        """Return the identifiers of the device of a button."""
        entity_id = entity_registry.async_get_entity_id(
            BUTTON_DOMAIN, DOMAIN, unique_id
        )
        entity_entry = entity_registry.async_get(entity_id)
        return device_registry.async_get(entity_entry.device_id).identifiers

    assert device_identifiers(f"{SERIAL}_ch0000_button") == {multi_device_identifier}
    assert device_identifiers("ABB700000002_ch0000_button") == {
        (DOMAIN, "ABB700000002")
    }
