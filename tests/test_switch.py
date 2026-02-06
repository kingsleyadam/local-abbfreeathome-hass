"""Test for switch platform."""

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.switch import (
    FreeAtHomeSwitchEntity,
    async_setup_entry,
)
from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_switch_channel():
    """Create a mock switch channel."""
    channel = Mock()
    channel.device_id = "ABB_SWITCH"
    channel.device_serial = "ABB_SWITCH"
    channel.channel_id = "ch0000"
    channel.channel_name = "Switch Channel"
    channel.room_name = "Living Room"
    channel.device_name = "Switch Device"
    channel.device.is_multi_device = False
    channel.device.device_id = "ABB_SWITCH_DEV"

    # Attributes for different switch types
    channel.led = True
    channel.state = False
    channel.alarm = True
    channel.eco_mode = False
    channel.blocked = False

    channel.turn_on = AsyncMock()
    channel.turn_off = AsyncMock()

    # Custom methods
    channel.turn_on_led = AsyncMock()
    channel.turn_off_led = AsyncMock()

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
    """Test setup entry with no switch devices."""
    mock_free_at_home.get_channels_by_class.return_value = []
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}
    async_add_entities = Mock()

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # There are 13 switch descriptions
    assert async_add_entities.call_count == 13
    for call in async_add_entities.call_args_list:
        assert len(list(call[0][0])) == 0


async def test_async_setup_entry_with_devices(
    hass: HomeAssistant,
    mock_config_entry,
    mock_free_at_home,
    mock_switch_channel,
):
    """Test setup entry with switch devices."""
    mock_free_at_home.get_channels_by_class.return_value = [mock_switch_channel]
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}
    async_add_entities = Mock()

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert async_add_entities.call_count == 13
    for call in async_add_entities.call_args_list:
        assert len(list(call[0][0])) == 1


async def test_switch_entity_generic(mock_switch_channel):
    """Test generic switch entity (using default turn_on/off)."""
    # Ensure specific turn_on/off methods don't exist/aren't callable
    mock_switch_channel.turn_on_state = None
    mock_switch_channel.turn_off_state = None

    entity = FreeAtHomeSwitchEntity(
        mock_switch_channel,
        value_attribute="state",
        entity_description_kwargs={"key": "test_switch"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )

    assert entity.is_on is False

    await entity.async_turn_on()
    mock_switch_channel.turn_on.assert_called_once()

    await entity.async_turn_off()
    mock_switch_channel.turn_off.assert_called_once()


async def test_switch_entity_custom_method(mock_switch_channel):
    """Test switch entity with custom turn_on/off methods."""
    # Ensure attributes and methods exist on the mock
    mock_switch_channel.led = True

    entity = FreeAtHomeSwitchEntity(
        mock_switch_channel,
        value_attribute="led",
        entity_description_kwargs={"key": "test_switch_led"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )

    assert entity.is_on is True

    await entity.async_turn_on()
    mock_switch_channel.turn_on_led.assert_called_once()

    await entity.async_turn_off()
    mock_switch_channel.turn_off_led.assert_called_once()


async def test_callbacks(mock_switch_channel):
    """Test callbacks."""
    entity = FreeAtHomeSwitchEntity(
        mock_switch_channel,
        value_attribute="state",
        entity_description_kwargs={"key": "test_switch"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )

    await entity.async_added_to_hass()
    mock_switch_channel.register_callback.assert_called_with(
        callback_attribute="state", callback=entity.async_write_ha_state
    )

    await entity.async_will_remove_from_hass()
    mock_switch_channel.remove_callback.assert_called_with(
        callback_attribute="state", callback=entity.async_write_ha_state
    )


async def test_device_info(mock_switch_channel):
    """Test device info."""
    entity = FreeAtHomeSwitchEntity(
        mock_switch_channel,
        value_attribute="state",
        entity_description_kwargs={"key": "test_switch"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )
    assert entity.device_info["identifiers"] == {(DOMAIN, "ABB_SWITCH")}

    mock_switch_channel.device.is_multi_device = True
    entity = FreeAtHomeSwitchEntity(
        mock_switch_channel,
        value_attribute="state",
        entity_description_kwargs={"key": "test_switch"},
        sysap_serial_number="SERIAL",
        create_subdevices=True,
    )
    assert entity.device_info["identifiers"] == {(DOMAIN, "ABB_SWITCH_ch0000")}


async def test_unique_id(mock_switch_channel):
    """Test unique id."""
    entity = FreeAtHomeSwitchEntity(
        mock_switch_channel,
        value_attribute="state",
        entity_description_kwargs={"key": "MyKey", "translation_key": "my_key"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )
    # If translation_key is present, unique_id includes key
    assert entity.unique_id == "ABB_SWITCH_ch0000_MyKey"

    # If translation_key is missing (or None), unique_id uses _switch suffix (default in switch.py?)
    # switch.py logic:
    # if hasattr(self.entity_description, "translation_key") and self.entity_description.translation_key is not None:
    #     return ... key
    # return ... _switch

    entity_no_key = FreeAtHomeSwitchEntity(
        mock_switch_channel,
        value_attribute="state",
        entity_description_kwargs={"key": "MyKey"},  # no translation_key
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )
    # entity_description defaults translation_key to None?
    # Actually SwitchEntityDescription defaults translation_key to None
    assert entity_no_key.unique_id == "ABB_SWITCH_ch0000_switch"


async def test_translation_key(mock_switch_channel):
    """Test translation key property."""
    entity = FreeAtHomeSwitchEntity(
        mock_switch_channel,
        value_attribute="state",
        entity_description_kwargs={"key": "MyKey", "translation_key": "my_trans_key"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )
    assert entity.translation_key == "my_trans_key"

    # Test fallback behavior logic in code?
    # property translation_key:
    # if hasattr(self, "_attr_translation_key"): ...
    # if hasattr(self, "entity_description"): ...

    entity2 = FreeAtHomeSwitchEntity(
        mock_switch_channel,
        value_attribute="state",
        entity_description_kwargs={"key": "MyKey"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )
    assert entity2.translation_key is None


async def test_async_update(hass: HomeAssistant, mock_switch_channel):
    """Test async update."""
    entity = FreeAtHomeSwitchEntity(
        mock_switch_channel,
        value_attribute="state",
        entity_description_kwargs={"key": "test_switch"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )
    entity.hass = hass

    await entity.async_update()
    mock_switch_channel.refresh_state.assert_called_once()


async def test_translation_key_attr(mock_switch_channel):
    """Test translation_key from _attr_translation_key."""
    entity = FreeAtHomeSwitchEntity(
        mock_switch_channel,
        value_attribute="state",
        entity_description_kwargs={"key": "test"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )
    entity._attr_translation_key = "attr_key"
    # Delete entity_description to allow _attr_translation_key to persist
    del entity.entity_description
    assert entity.translation_key == "attr_key"
