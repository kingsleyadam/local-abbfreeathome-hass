"""Test for select platform."""

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.select import (
    FreeAtHomeSelectEntity,
    async_setup_entry,
)
from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_select_channel():
    """Create a mock select channel."""
    channel = Mock()
    channel.device_id = "ABB_SELECT"
    channel.device_serial = "ABB_SELECT"
    channel.channel_id = "ch0000"
    channel.channel_name = "Select Channel"
    channel.room_name = "Living Room"
    channel.device_name = "Select Device"
    channel.device.is_multi_device = False
    channel.device.device_id = "ABB_SELECT_DEV"

    channel.forced_position = "off"

    channel.set_forced_position = AsyncMock()
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
    """Test setup entry with no select devices."""
    mock_free_at_home.get_channels_by_class.return_value = []
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}
    async_add_entities = Mock()

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # There are 6 select descriptions
    assert async_add_entities.call_count == 6
    for call in async_add_entities.call_args_list:
        assert len(list(call[0][0])) == 0


async def test_async_setup_entry_with_devices(
    hass: HomeAssistant,
    mock_config_entry,
    mock_free_at_home,
    mock_select_channel,
):
    """Test setup entry with select devices."""
    mock_free_at_home.get_channels_by_class.return_value = [mock_select_channel]
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}
    async_add_entities = Mock()

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert async_add_entities.call_count == 6
    for call in async_add_entities.call_args_list:
        assert len(list(call[0][0])) == 1


async def test_select_entity(mock_select_channel):
    """Test select entity properties and methods."""
    entity = FreeAtHomeSelectEntity(
        mock_select_channel,
        entity_description_kwargs={"key": "test_select", "options": ["off", "on"]},
        current_option_attribute="forced_position",
        select_option_method="set_forced_position",
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )

    assert entity.current_option == "off"

    await entity.async_select_option("on")
    mock_select_channel.set_forced_position.assert_called_with("on")


async def test_callbacks(mock_select_channel):
    """Test callbacks."""
    entity = FreeAtHomeSelectEntity(
        mock_select_channel,
        entity_description_kwargs={"key": "test_select", "options": ["off", "on"]},
        current_option_attribute="forced_position",
        select_option_method="set_forced_position",
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )

    await entity.async_added_to_hass()
    mock_select_channel.register_callback.assert_called_with(
        callback_attribute="forced_position", callback=entity.async_write_ha_state
    )

    await entity.async_will_remove_from_hass()
    mock_select_channel.remove_callback.assert_called_with(
        callback_attribute="forced_position", callback=entity.async_write_ha_state
    )


async def test_device_info(mock_select_channel):
    """Test device info."""
    entity = FreeAtHomeSelectEntity(
        mock_select_channel,
        entity_description_kwargs={"key": "test_select"},
        current_option_attribute="forced_position",
        select_option_method="set_forced_position",
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )
    assert entity.device_info["identifiers"] == {(DOMAIN, "ABB_SELECT")}

    mock_select_channel.device.is_multi_device = True
    entity = FreeAtHomeSelectEntity(
        mock_select_channel,
        entity_description_kwargs={"key": "test_select"},
        current_option_attribute="forced_position",
        select_option_method="set_forced_position",
        sysap_serial_number="SERIAL",
        create_subdevices=True,
    )
    assert entity.device_info["identifiers"] == {(DOMAIN, "ABB_SELECT_ch0000")}


async def test_unique_id(mock_select_channel):
    """Test unique id."""
    entity = FreeAtHomeSelectEntity(
        mock_select_channel,
        entity_description_kwargs={"key": "MyKey"},
        current_option_attribute="forced_position",
        select_option_method="set_forced_position",
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )
    assert entity.unique_id == "ABB_SELECT_ch0000_MyKey"
