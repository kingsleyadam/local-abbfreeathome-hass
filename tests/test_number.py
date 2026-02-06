"""Test for number platform."""

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.number import (
    FreeAtHomeNumberEntity,
    async_setup_entry,
)
from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_number_channel():
    """Create a mock number channel."""
    channel = Mock()
    channel.device_id = "ABB_NUMBER"
    channel.device_serial = "ABB_NUMBER"
    channel.channel_id = "ch0000"
    channel.channel_name = "Number Channel"
    channel.room_name = "Living Room"
    channel.device_name = "Number Device"
    channel.device.is_multi_device = False
    channel.device.device_id = "ABB_NUMBER_DEV"

    # Attributes for different number types
    channel.brightness = 500.0
    channel.battery_power = 10.5
    channel.soc = 80.0
    channel.imported_today = 1000.0
    channel.exported_today = 500.0
    channel.imported_total = 10000.0
    channel.exported_total = 5000.0
    channel.current_power = 200.0
    channel.current_temperature = 21.0
    channel.target_temperature = 22.0
    channel.temperature = 20.0
    channel.force = 3.0
    channel.speed = 5.0

    # Set methods
    channel.set_brightness = AsyncMock()
    channel.set_battery_power = AsyncMock()  # unlikely to exist but follows pattern
    channel.set_soc = AsyncMock()  # unlikely
    channel.set_target_temperature = AsyncMock()

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
    """Test setup entry with no number devices."""
    mock_free_at_home.get_channels_by_class.return_value = []
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}
    async_add_entities = Mock()

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # There are 20 number descriptions
    assert async_add_entities.call_count == 20
    for call in async_add_entities.call_args_list:
        assert len(list(call[0][0])) == 0


async def test_async_setup_entry_with_devices(
    hass: HomeAssistant,
    mock_config_entry,
    mock_free_at_home,
    mock_number_channel,
):
    """Test setup entry with number devices."""
    mock_free_at_home.get_channels_by_class.return_value = [mock_number_channel]
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}
    async_add_entities = Mock()

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert async_add_entities.call_count == 20
    for call in async_add_entities.call_args_list:
        assert len(list(call[0][0])) == 1


async def test_number_entity(mock_number_channel):
    """Test number entity properties and methods."""
    entity = FreeAtHomeNumberEntity(
        mock_number_channel,
        value_attribute="brightness",
        entity_description_kwargs={"key": "test_number"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )

    assert entity.native_value == 500.0

    await entity.async_set_native_value(600.0)
    mock_number_channel.set_brightness.assert_called_with(600.0)

    # Test update
    await entity.async_update()
    mock_number_channel.refresh_state.assert_called_once()


async def test_callbacks(mock_number_channel):
    """Test callbacks."""
    entity = FreeAtHomeNumberEntity(
        mock_number_channel,
        value_attribute="brightness",
        entity_description_kwargs={"key": "test_number"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )

    await entity.async_added_to_hass()
    mock_number_channel.register_callback.assert_called_with(
        callback_attribute="brightness", callback=entity.async_write_ha_state
    )

    await entity.async_will_remove_from_hass()
    mock_number_channel.remove_callback.assert_called_with(
        callback_attribute="brightness", callback=entity.async_write_ha_state
    )


async def test_device_info(mock_number_channel):
    """Test device info."""
    entity = FreeAtHomeNumberEntity(
        mock_number_channel,
        value_attribute="brightness",
        entity_description_kwargs={"key": "test_number"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )
    assert entity.device_info["identifiers"] == {(DOMAIN, "ABB_NUMBER")}

    mock_number_channel.device.is_multi_device = True
    entity = FreeAtHomeNumberEntity(
        mock_number_channel,
        value_attribute="brightness",
        entity_description_kwargs={"key": "test_number"},
        sysap_serial_number="SERIAL",
        create_subdevices=True,
    )
    assert entity.device_info["identifiers"] == {(DOMAIN, "ABB_NUMBER_ch0000")}


async def test_unique_id(mock_number_channel):
    """Test unique id."""
    entity = FreeAtHomeNumberEntity(
        mock_number_channel,
        value_attribute="brightness",
        entity_description_kwargs={"key": "MyKey"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )
    assert entity.unique_id == "ABB_NUMBER_ch0000_MyKey"
