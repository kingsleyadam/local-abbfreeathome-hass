"""Test repair issues for unresponsive ABB-free@home devices."""

from unittest.mock import AsyncMock, MagicMock

from abbfreeathome import DevicesChangedEvent
from abbfreeathome.bin.interface import Interface
from abbfreeathome.device import Device
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.abbfreeathome_ci import async_remove_config_entry_device
from custom_components.abbfreeathome_ci.const import (
    CONF_CREATE_UNRESPONSIVE_REPAIRS,
    DOMAIN,
    UNRESPONSIVE_REPAIR_DELAY,
)
from custom_components.abbfreeathome_ci.unresponsive import (
    async_get_unresponsive_tracker,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, issue_registry as ir

from .test_init import _devices_changed, _setup_with_channels, _trigger

SERIAL = "ABB700000001"


@pytest.fixture(autouse=True)
def no_platforms(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the entity platforms, the tracker works on devices only."""
    monkeypatch.setattr("custom_components.abbfreeathome_ci.PLATFORMS", [])


@pytest.fixture
def mock_free_at_home_settings() -> MagicMock:
    """Mock FreeAtHomeSettings with serializable values."""
    mock = MagicMock()
    mock.load = AsyncMock()
    mock.name = "Test SysAP"
    mock.version = "3.0.0"
    mock.hardware_version = "1.0"
    mock.serial_number = "TEST123456"
    return mock


@pytest.fixture
def repairs_config_entry(mock_config_entry: MockConfigEntry) -> MockConfigEntry:
    """Return a config entry with unresponsive repairs enabled."""
    return MockConfigEntry(
        version=mock_config_entry.version,
        minor_version=mock_config_entry.minor_version,
        domain=DOMAIN,
        title=mock_config_entry.title,
        data={**mock_config_entry.data, CONF_CREATE_UNRESPONSIVE_REPAIRS: True},
        source=mock_config_entry.source,
        unique_id=mock_config_entry.unique_id,
    )


def _device(
    serial: str = SERIAL,
    *,
    unresponsive: bool = False,
    interface: Interface | None = None,
) -> Device:
    """Build a real free@home device."""
    return Device(
        serial,
        "1234",
        "Runtime Device",
        api=MagicMock(),
        interface=interface,
        unresponsive=unresponsive,
    )


def _issue(hass: HomeAssistant, entry: MockConfigEntry, serial: str = SERIAL):
    """Return the repair issue of a device, if any."""
    return ir.async_get(hass).async_get_issue(
        DOMAIN, f"unresponsive_{entry.entry_id}_{serial}"
    )


async def _pass_delay(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, factor: float = 1
) -> None:
    """Advance the time by a share of the repair delay."""
    freezer.tick(UNRESPONSIVE_REPAIR_DELAY * factor)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_disabled_by_default(
    hass: HomeAssistant, mock_config_entry, mock_free_at_home_settings, freezer
) -> None:
    """Test no repair issue is created when the option is disabled."""
    device = _device(unresponsive=True)
    await _setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [_trigger(device)]
    )

    await _pass_delay(hass, freezer, 2)

    assert _issue(hass, mock_config_entry) is None


async def test_unresponsive_at_startup(
    hass: HomeAssistant, repairs_config_entry, mock_free_at_home_settings, freezer
) -> None:
    """Test a device unresponsive at startup gets an issue after the delay."""
    device = _device(unresponsive=True)
    await _setup_with_channels(
        hass, repairs_config_entry, mock_free_at_home_settings, [_trigger(device)]
    )

    await _pass_delay(hass, freezer, 0.5)
    assert _issue(hass, repairs_config_entry) is None

    await _pass_delay(hass, freezer, 1)
    issue = _issue(hass, repairs_config_entry)
    assert issue is not None
    assert issue.translation_key == "device_unresponsive"
    assert issue.translation_placeholders == {
        "name": "Runtime Device",
        "serial": SERIAL,
    }
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.is_fixable is False
    assert issue.is_persistent is False


async def test_repeated_report_keeps_delay(
    hass: HomeAssistant, repairs_config_entry, mock_free_at_home_settings, freezer
) -> None:
    """Test a repeated unresponsive report does not restart the delay."""
    device = _device(unresponsive=True)
    await _setup_with_channels(
        hass, repairs_config_entry, mock_free_at_home_settings, [_trigger(device)]
    )
    tracker = async_get_unresponsive_tracker(hass, repairs_config_entry.entry_id)

    await _pass_delay(hass, freezer, 0.6)
    tracker._async_update(device)
    await _pass_delay(hass, freezer, 0.6)

    assert _issue(hass, repairs_config_entry) is not None


async def test_recovers_within_delay(
    hass: HomeAssistant, repairs_config_entry, mock_free_at_home_settings, freezer
) -> None:
    """Test a brief dropout does not create an issue."""
    device = _device()
    await _setup_with_channels(
        hass, repairs_config_entry, mock_free_at_home_settings, [_trigger(device)]
    )

    device.update_unresponsive(True)
    await _pass_delay(hass, freezer, 0.5)
    device.update_unresponsive(False)
    await _pass_delay(hass, freezer, 2)

    assert _issue(hass, repairs_config_entry) is None


async def test_issue_removed_when_device_responds(
    hass: HomeAssistant, repairs_config_entry, mock_free_at_home_settings, freezer
) -> None:
    """Test the issue is removed once the device responds again."""
    device = _device()
    await _setup_with_channels(
        hass, repairs_config_entry, mock_free_at_home_settings, [_trigger(device)]
    )

    device.update_unresponsive(True)
    await _pass_delay(hass, freezer, 1.5)
    assert _issue(hass, repairs_config_entry) is not None

    device.update_unresponsive(False)
    await hass.async_block_till_done()
    assert _issue(hass, repairs_config_entry) is None


async def test_virtual_device(
    hass: HomeAssistant, repairs_config_entry, mock_free_at_home_settings, freezer
) -> None:
    """Test virtual devices get their own issue text."""
    device = _device(unresponsive=True, interface=Interface.VIRTUAL_DEVICE)
    await _setup_with_channels(
        hass, repairs_config_entry, mock_free_at_home_settings, [_trigger(device)]
    )

    await _pass_delay(hass, freezer, 1.5)

    issue = _issue(hass, repairs_config_entry)
    assert issue is not None
    assert issue.translation_key == "virtual_device_unresponsive"


async def test_device_without_visible_channels(
    hass: HomeAssistant, repairs_config_entry, mock_free_at_home_settings, freezer
) -> None:
    """Test devices without a device registry entry are not tracked."""
    mock_fah = await _setup_with_channels(
        hass, repairs_config_entry, mock_free_at_home_settings, []
    )
    device = _device(unresponsive=True)

    _devices_changed(mock_fah, DevicesChangedEvent(added_devices=(device,)))
    await _pass_delay(hass, freezer, 1.5)

    assert _issue(hass, repairs_config_entry) is None


async def test_runtime_device_added_and_removed(
    hass: HomeAssistant, repairs_config_entry, mock_free_at_home_settings, freezer
) -> None:
    """Test devices added at runtime are tracked until removed by the SysAP."""
    mock_fah = await _setup_with_channels(
        hass, repairs_config_entry, mock_free_at_home_settings, []
    )
    device = _device()
    channel = _trigger(device)
    mock_fah.channels.append(channel)

    _devices_changed(
        mock_fah,
        DevicesChangedEvent(added_devices=(device,), added_channels=(channel,)),
    )
    # A repeated channel must not track the device twice.
    _devices_changed(mock_fah, DevicesChangedEvent(added_channels=(channel,)))
    device.update_unresponsive(True)
    await _pass_delay(hass, freezer, 1.5)
    assert _issue(hass, repairs_config_entry) is not None

    mock_fah.channels.remove(channel)
    _devices_changed(
        mock_fah, DevicesChangedEvent(removed_device_serials=(SERIAL, "UNKNOWN"))
    )
    await hass.async_block_till_done()
    assert _issue(hass, repairs_config_entry) is None

    # The removed device must not report anymore.
    device.update_unresponsive(False)
    device.update_unresponsive(True)
    await _pass_delay(hass, freezer, 1.5)
    assert _issue(hass, repairs_config_entry) is None


async def test_removal_cancels_pending_issue(
    hass: HomeAssistant, repairs_config_entry, mock_free_at_home_settings, freezer
) -> None:
    """Test removing a device before the delay elapsed creates no issue."""
    device = _device(unresponsive=True)
    mock_fah = await _setup_with_channels(
        hass, repairs_config_entry, mock_free_at_home_settings, [_trigger(device)]
    )

    mock_fah.channels.clear()
    _devices_changed(mock_fah, DevicesChangedEvent(removed_device_serials=(SERIAL,)))
    await _pass_delay(hass, freezer, 1.5)

    assert _issue(hass, repairs_config_entry) is None


async def test_manual_device_removal(
    hass: HomeAssistant, repairs_config_entry, mock_free_at_home_settings, freezer
) -> None:
    """Test removing a device in Home Assistant removes its issue."""
    device = _device(unresponsive=True)
    await _setup_with_channels(
        hass, repairs_config_entry, mock_free_at_home_settings, [_trigger(device)]
    )
    await _pass_delay(hass, freezer, 1.5)
    assert _issue(hass, repairs_config_entry) is not None

    device_entry = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, SERIAL)})
    assert await async_remove_config_entry_device(
        hass, repairs_config_entry, device_entry
    )

    assert _issue(hass, repairs_config_entry) is None


async def test_unload_removes_issues(
    hass: HomeAssistant, repairs_config_entry, mock_free_at_home_settings, freezer
) -> None:
    """Test unloading the entry removes issues and pending timers."""
    first = _device(unresponsive=True)
    second = _device("ABB700000002")
    await _setup_with_channels(
        hass,
        repairs_config_entry,
        mock_free_at_home_settings,
        [_trigger(first), _trigger(second)],
    )
    await _pass_delay(hass, freezer, 1.5)
    second.update_unresponsive(True)
    assert _issue(hass, repairs_config_entry) is not None

    assert await hass.config_entries.async_unload(repairs_config_entry.entry_id)
    await _pass_delay(hass, freezer, 1.5)

    assert _issue(hass, repairs_config_entry) is None
    assert _issue(hass, repairs_config_entry, "ABB700000002") is None
