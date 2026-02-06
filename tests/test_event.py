"""Test for event platform."""

from unittest.mock import Mock

import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.event import (
    FreeAtHomeEventEntity,
    async_setup_entry,
)
from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_event_channel():
    """Create a mock event channel."""
    channel = Mock()
    channel.device_id = "ABB_EVENT"
    channel.device_serial = "ABB_EVENT"
    channel.channel_id = "ch0000"
    channel.channel_name = "Event Channel"
    channel.room_name = "Living Room"
    channel.device_name = "Event Device"
    channel.device.is_multi_device = False
    channel.device.device_id = "ABB_EVENT_DEV"

    # Attributes for different event types
    channel.state = "On"
    channel.requested_state = True
    channel.requested_eco_mode = False
    channel.requested_target_temperature = 22.0

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
    """Test setup entry with no event devices."""
    mock_free_at_home.get_channels_by_class.return_value = []
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}
    async_add_entities = Mock()

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # There are 9 event descriptions
    assert async_add_entities.call_count == 9
    for call in async_add_entities.call_args_list:
        assert len(list(call[0][0])) == 0


async def test_async_setup_entry_with_devices(
    hass: HomeAssistant,
    mock_config_entry,
    mock_free_at_home,
    mock_event_channel,
):
    """Test setup entry with event devices."""
    # We want at least one list to contain the mock channel
    # Since get_channels_by_class is called 9 times, we can use side_effect
    # or just return a list for all calls.
    mock_free_at_home.get_channels_by_class.return_value = [mock_event_channel]
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}
    async_add_entities = Mock()

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert async_add_entities.call_count == 9
    for call in async_add_entities.call_args_list:
        assert len(list(call[0][0])) == 1


async def test_event_entity_handle_event(hass, mock_event_channel):
    """Test event handling."""
    # Test simple event entity (e.g. SwitchSensor)
    entity = FreeAtHomeEventEntity(
        mock_event_channel,
        state_attribute="state",
        entity_description_kwargs={"key": "test_event", "event_types": ["On", "Off"]},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
        event_type_callback=lambda state: state,
    )
    entity.hass = hass
    # Patch _trigger_event to check if called
    entity._trigger_event = Mock()
    entity.async_write_ha_state = Mock()

    # Trigger event
    entity._async_handle_event()

    entity._trigger_event.assert_called_with("On", {"extra_data": None})
    entity.async_write_ha_state.assert_called()


async def test_event_entity_handle_event_no_attribute(hass):
    """Test event handling without state attribute."""
    # Use a mock with spec to prevent hasattr from returning True for ""
    channel = Mock(
        spec=[
            "channel_name",
            "channel_id",
            "device_serial",
            "device_name",
            "room_name",
            "device",
            "register_callback",
            "remove_callback",
        ]
    )
    channel.channel_name = "Event Channel"
    channel.channel_id = "ch0000"
    channel.device_serial = "ABB_EVENT"
    channel.device_name = "Event Device"
    channel.room_name = "Living Room"
    channel.device = Mock()
    channel.device.is_multi_device = False
    channel.device.device_id = "ABB_EVENT_DEV"
    channel.register_callback = Mock()
    channel.remove_callback = Mock()

    entity = FreeAtHomeEventEntity(
        channel,
        state_attribute="",
        entity_description_kwargs={
            "key": "test_event_no_attr",
            "event_types": ["activated"],
        },
        sysap_serial_number="SERIAL",
        create_subdevices=False,
        event_type_callback=lambda: "activated",
    )
    entity.hass = hass
    entity._trigger_event = Mock()
    entity.async_write_ha_state = Mock()

    entity._async_handle_event()

    entity._trigger_event.assert_called_with("activated", {"extra_data": None})


async def test_event_entity_extra_data(hass, mock_event_channel):
    """Test event handling with extra data."""
    mock_event_channel.extra_val = "some_data"

    entity = FreeAtHomeEventEntity(
        mock_event_channel,
        state_attribute="state",
        entity_description_kwargs={"key": "test_event_extra"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
        event_type_callback=lambda state: state,
        extra_data="extra_val",
    )
    entity.hass = hass
    entity._trigger_event = Mock()
    entity.async_write_ha_state = Mock()

    entity._async_handle_event()

    entity._trigger_event.assert_called_with("On", {"extra_data": "some_data"})


async def test_callbacks(mock_event_channel):
    """Test callbacks registration."""
    # With state attribute
    entity = FreeAtHomeEventEntity(
        mock_event_channel,
        state_attribute="state",
        entity_description_kwargs={"key": "test"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
        event_type_callback=lambda x: x,
    )
    await entity.async_added_to_hass()
    mock_event_channel.register_callback.assert_called_with(
        callback_attribute="state", callback=entity._async_handle_event
    )

    await entity.async_will_remove_from_hass()
    mock_event_channel.remove_callback.assert_called_with(
        callback_attribute="state", callback=entity._async_handle_event
    )

    # Without state attribute
    entity2 = FreeAtHomeEventEntity(
        mock_event_channel,
        state_attribute="",
        entity_description_kwargs={"key": "test2"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
        event_type_callback=lambda: "x",
    )
    await entity2.async_added_to_hass()
    # Should default to "state" callback for monitoring but use empty attribute logic in handler?
    # Code says: if len(self._state_attribute) > 0: ... else: callback_attribute="state"
    mock_event_channel.register_callback.assert_called_with(
        callback_attribute="state", callback=entity2._async_handle_event
    )

    await entity2.async_will_remove_from_hass()
    mock_event_channel.remove_callback.assert_called_with(
        callback_attribute="state", callback=entity2._async_handle_event
    )


async def test_device_info(mock_event_channel):
    """Test device info."""
    entity = FreeAtHomeEventEntity(
        mock_event_channel,
        state_attribute="state",
        entity_description_kwargs={"key": "test"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
        event_type_callback=lambda x: x,
    )
    assert entity.device_info["identifiers"] == {(DOMAIN, "ABB_EVENT")}

    mock_event_channel.device.is_multi_device = True
    entity = FreeAtHomeEventEntity(
        mock_event_channel,
        state_attribute="state",
        entity_description_kwargs={"key": "test"},
        sysap_serial_number="SERIAL",
        create_subdevices=True,
        event_type_callback=lambda x: x,
    )
    assert entity.device_info["identifiers"] == {(DOMAIN, "ABB_EVENT_ch0000")}


async def test_unique_id(mock_event_channel):
    """Test unique id."""
    entity = FreeAtHomeEventEntity(
        mock_event_channel,
        state_attribute="state",
        entity_description_kwargs={"key": "MyKey"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
        event_type_callback=lambda x: x,
    )
    assert entity.unique_id == "ABB_EVENT_ch0000_MyKey"
