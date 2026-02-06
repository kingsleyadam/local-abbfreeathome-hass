"""Test for sensor platform."""

from unittest.mock import Mock

import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.sensor import (
    FreeAtHomeSensorEntity,
    async_setup_entry,
)
from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_sensor_channel():
    """Create a mock sensor channel."""
    channel = Mock()
    channel.device_id = "ABB_SENSOR"
    channel.device_serial = "ABB_SENSOR"
    channel.channel_id = "ch0000"
    channel.channel_name = "Sensor Channel"
    channel.room_name = "Living Room"
    channel.device_name = "Sensor Device"
    channel.device.is_multi_device = False
    channel.device.device_id = "ABB_SENSOR_DEV"

    # Attributes for different sensor types
    channel.co2 = 500
    channel.voc_index = 100
    channel.humidity = 45.0
    channel.state = 21.0
    channel.brightness = 300.0
    channel.position = "open"
    channel.force = 2.0

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
    """Test setup entry with no sensor devices."""
    mock_free_at_home.get_channels_by_class.return_value = []
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}
    async_add_entities = Mock()

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # There are 10 sensor descriptions
    assert async_add_entities.call_count == 10
    for call in async_add_entities.call_args_list:
        assert len(list(call[0][0])) == 0


async def test_async_setup_entry_with_devices(
    hass: HomeAssistant,
    mock_config_entry,
    mock_free_at_home,
    mock_sensor_channel,
):
    """Test setup entry with sensor devices."""
    mock_free_at_home.get_channels_by_class.return_value = [mock_sensor_channel]
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}
    async_add_entities = Mock()

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert async_add_entities.call_count == 10
    for call in async_add_entities.call_args_list:
        assert len(list(call[0][0])) == 1


async def test_sensor_entity(mock_sensor_channel):
    """Test sensor entity properties."""
    entity = FreeAtHomeSensorEntity(
        mock_sensor_channel,
        value_attribute="state",
        entity_description_kwargs={"key": "test_sensor"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )

    assert entity.native_value == 21.0


async def test_callbacks(mock_sensor_channel):
    """Test callbacks."""
    entity = FreeAtHomeSensorEntity(
        mock_sensor_channel,
        value_attribute="state",
        entity_description_kwargs={"key": "test_sensor"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )

    await entity.async_added_to_hass()
    mock_sensor_channel.register_callback.assert_called_with(
        callback_attribute="state", callback=entity.async_write_ha_state
    )

    await entity.async_will_remove_from_hass()
    mock_sensor_channel.remove_callback.assert_called_with(
        callback_attribute="state", callback=entity.async_write_ha_state
    )


async def test_device_info(mock_sensor_channel):
    """Test device info."""
    entity = FreeAtHomeSensorEntity(
        mock_sensor_channel,
        value_attribute="state",
        entity_description_kwargs={"key": "test_sensor"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )
    assert entity.device_info["identifiers"] == {(DOMAIN, "ABB_SENSOR")}

    mock_sensor_channel.device.is_multi_device = True
    entity = FreeAtHomeSensorEntity(
        mock_sensor_channel,
        value_attribute="state",
        entity_description_kwargs={"key": "test_sensor"},
        sysap_serial_number="SERIAL",
        create_subdevices=True,
    )
    assert entity.device_info["identifiers"] == {(DOMAIN, "ABB_SENSOR_ch0000")}


async def test_unique_id(mock_sensor_channel):
    """Test unique id."""
    entity = FreeAtHomeSensorEntity(
        mock_sensor_channel,
        value_attribute="state",
        entity_description_kwargs={"key": "MyKey"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )
    assert entity.unique_id == "ABB_SENSOR_ch0000_MyKey"
