"""Test for lock platform."""

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.lock import (
    FreeAtHomeLockEntity,
    async_setup_entry,
)
from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_lock_channel():
    """Create a mock lock channel."""
    channel = Mock()
    channel.device_id = "ABB_LOCK"
    channel.device_serial = "ABB_LOCK"
    channel.channel_id = "ch0000"
    channel.channel_name = "Lock Channel"
    channel.room_name = "Hallway"
    channel.device_name = "Door Opener"
    channel.device.is_multi_device = False
    channel.device.device_id = "ABB_LOCK_DEV"

    channel.state = False  # False means Locked in the implementation

    channel.lock = AsyncMock()
    channel.unlock = AsyncMock()
    channel.refresh_state = AsyncMock()
    channel.register_callback = Mock()
    channel.remove_callback = Mock()
    return channel


@pytest.fixture
def mock_free_at_home():
    """Create a mock FreeAtHome API object."""
    api = Mock()
    api.get_channels_by_class = Mock(return_value=[])
    return api


async def test_async_setup_entry_no_devices(
    hass: HomeAssistant, mock_config_entry, mock_free_at_home
):
    """Test setup entry with no lock devices."""
    mock_free_at_home.get_channels_by_class.return_value = []
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}
    async_add_entities = Mock()

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    async_add_entities.assert_called_once()
    assert len(list(async_add_entities.call_args[0][0])) == 0


async def test_async_setup_entry_with_devices(
    hass: HomeAssistant,
    mock_config_entry,
    mock_free_at_home,
    mock_lock_channel,
):
    """Test setup entry with lock devices."""
    mock_free_at_home.get_channels_by_class.return_value = [mock_lock_channel]
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}
    async_add_entities = Mock()

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    async_add_entities.assert_called_once()
    assert len(list(async_add_entities.call_args[0][0])) == 1


async def test_lock_state(mock_lock_channel):
    """Test lock state."""
    entity = FreeAtHomeLockEntity(
        mock_lock_channel,
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )

    mock_lock_channel.state = False
    assert entity.is_locked

    mock_lock_channel.state = True
    assert not entity.is_locked

    # Check if None handling is required?
    # The code says `return self._channel.state is False`.
    # So None is not False, returns False (unlocked).
    mock_lock_channel.state = None
    assert not entity.is_locked


async def test_async_lock(mock_lock_channel):
    """Test async lock."""
    entity = FreeAtHomeLockEntity(
        mock_lock_channel,
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )

    await entity.async_lock()
    mock_lock_channel.lock.assert_called_once()


async def test_async_unlock(mock_lock_channel):
    """Test async unlock."""
    entity = FreeAtHomeLockEntity(
        mock_lock_channel,
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )

    await entity.async_unlock()
    mock_lock_channel.unlock.assert_called_once()


async def test_async_update(hass: HomeAssistant, mock_lock_channel):
    """Test async update."""
    entity = FreeAtHomeLockEntity(
        mock_lock_channel,
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )
    entity.hass = hass

    await entity.async_update()
    mock_lock_channel.refresh_state.assert_called_once()


async def test_callbacks(mock_lock_channel):
    """Test callbacks."""
    entity = FreeAtHomeLockEntity(
        mock_lock_channel,
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )

    await entity.async_added_to_hass()
    mock_lock_channel.register_callback.assert_called_with(
        callback_attribute="state", callback=entity.async_write_ha_state
    )

    await entity.async_will_remove_from_hass()
    mock_lock_channel.remove_callback.assert_called_with(
        callback_attribute="state", callback=entity.async_write_ha_state
    )


async def test_device_info(mock_lock_channel):
    """Test device info."""
    entity = FreeAtHomeLockEntity(
        mock_lock_channel,
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )
    assert entity.device_info["identifiers"] == {(DOMAIN, "ABB_LOCK")}

    mock_lock_channel.device.is_multi_device = True
    entity = FreeAtHomeLockEntity(
        mock_lock_channel,
        sysap_serial_number="SERIAL",
        create_subdevices=True,
    )
    assert entity.device_info["identifiers"] == {(DOMAIN, "ABB_LOCK_ch0000")}


async def test_unique_id(mock_lock_channel):
    """Test unique id."""
    entity = FreeAtHomeLockEntity(
        mock_lock_channel,
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )
    assert entity.unique_id == "ABB_LOCK_ch0000_valve"  # Code says _valve in lock.py ??
    # Checked lock.py: return f"{self._channel.device_serial}_{self._channel.channel_id}_valve"
    # Yes, it says _valve. Copy-paste error in original code likely, but I must test what is there.
