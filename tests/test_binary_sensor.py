"""Test ABB-free@home binary sensor."""

from unittest.mock import MagicMock

from abbfreeathome.channels.window_door_sensor import WindowDoorSensor

from custom_components.abbfreeathome_ci.binary_sensor import (
    FreeAtHomeBinarySensorEntity,
    async_setup_entry,
)
from custom_components.abbfreeathome_ci.const import DOMAIN
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.core import HomeAssistant


async def test_async_setup_entry_no_sensors(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup with no binary sensors."""
    mock_config_entry.add_to_hass(hass)

    mock_free_at_home = MagicMock()
    mock_free_at_home.get_channels_by_class.return_value = []
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    async_add_entities = MagicMock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # Should be called 11 times (once per sensor description) even if with empty lists
    assert async_add_entities.call_count == 11


async def test_async_setup_entry_with_window_sensor(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup with a window/door sensor."""
    mock_config_entry.add_to_hass(hass)

    # Create a mock window sensor channel
    mock_channel = MagicMock()
    mock_channel.channel_name = "Front Door"
    mock_channel.channel_id = "ch0000"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.device_name = "Door Sensor"
    mock_channel.room_name = "Entrance"
    mock_channel.state = True
    mock_channel.device.is_multi_device = False

    mock_free_at_home = MagicMock()

    def get_channels_by_class_side_effect(channel_class):
        """Return channels only for WindowDoorSensor."""
        if channel_class.__name__ == "WindowDoorSensor":
            return [mock_channel]
        return []

    mock_free_at_home.get_channels_by_class.side_effect = (
        get_channels_by_class_side_effect
    )
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    entities_added = []

    def capture_entities(entity_generator):
        """Capture entities from generator."""
        entities = list(entity_generator)
        entities_added.extend(entities)

    async_add_entities = MagicMock(side_effect=capture_entities)
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # Should have added 1 entity
    assert len(entities_added) == 1
    entity = entities_added[0]

    assert isinstance(entity, FreeAtHomeBinarySensorEntity)
    assert entity.entity_description.name == "Front Door"
    assert entity.unique_id == "ABB7F57FFFE12345_ch0000_WindowDoorSensorOnOff"
    assert entity.is_on is True


async def test_binary_sensor_entity_properties(hass: HomeAssistant) -> None:
    """Test binary sensor entity properties."""
    mock_channel = MagicMock(spec=WindowDoorSensor)
    mock_channel.channel_name = "Kitchen Window"
    mock_channel.channel_id = "ch0001"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.device_name = "Window Sensor"
    mock_channel.room_name = "Kitchen"
    mock_channel.state = False
    mock_channel.device.is_multi_device = False

    entity = FreeAtHomeBinarySensorEntity(
        channel=mock_channel,
        value_attribute="state",
        entity_description_kwargs={
            "key": "WindowDoorSensorOnOff",
            "device_class": BinarySensorDeviceClass.WINDOW,
            "translation_key": "window_door",
        },
        sysap_serial_number="TEST123456",
        create_subdevices=False,
    )

    assert entity.entity_description.name == "Kitchen Window"
    assert entity.unique_id == "ABB7F57FFFE12345_ch0001_WindowDoorSensorOnOff"
    assert entity.is_on is False
    assert entity.should_poll is False
    assert entity.translation_key == "window_door"

    # Test device info
    device_info = entity.device_info
    assert device_info["identifiers"] == {(DOMAIN, "ABB7F57FFFE12345")}


async def test_binary_sensor_entity_with_subdevices(hass: HomeAssistant) -> None:
    """Test binary sensor entity with subdevices enabled."""
    mock_channel = MagicMock(spec=WindowDoorSensor)
    mock_channel.channel_name = "Bedroom Window"
    mock_channel.channel_id = "ch0002"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.device_name = "Multi Window Sensor"
    mock_channel.room_name = "Bedroom"
    mock_channel.state = True
    mock_channel.device.is_multi_device = True
    mock_channel.device.device_id = "4800"

    entity = FreeAtHomeBinarySensorEntity(
        channel=mock_channel,
        value_attribute="state",
        entity_description_kwargs={
            "key": "WindowDoorSensorOnOff",
            "device_class": BinarySensorDeviceClass.WINDOW,
            "translation_key": "window_door",
        },
        sysap_serial_number="TEST123456",
        create_subdevices=True,
    )

    # Test device info for subdevice
    device_info = entity.device_info
    assert device_info["identifiers"] == {(DOMAIN, "ABB7F57FFFE12345_ch0002")}
    assert device_info["name"] == "Multi Window Sensor (ch0002)"
    assert device_info["serial_number"] == "ABB7F57FFFE12345_ch0002"
    assert device_info["hw_version"] == "4800 (sub)"
    assert device_info["suggested_area"] == "Bedroom"
    assert device_info["via_device"] == (DOMAIN, "ABB7F57FFFE12345")


async def test_binary_sensor_entity_callbacks(hass: HomeAssistant) -> None:
    """Test binary sensor entity callback registration."""
    mock_channel = MagicMock(spec=WindowDoorSensor)
    mock_channel.channel_name = "Test Window"
    mock_channel.channel_id = "ch0003"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.state = False

    entity = FreeAtHomeBinarySensorEntity(
        channel=mock_channel,
        value_attribute="state",
        entity_description_kwargs={
            "key": "WindowDoorSensorOnOff",
            "device_class": BinarySensorDeviceClass.WINDOW,
            "translation_key": "window_door",
        },
        sysap_serial_number="TEST123456",
        create_subdevices=False,
    )

    # Mock the async_write_ha_state method
    entity.async_write_ha_state = MagicMock()

    # Test callback registration on add
    await entity.async_added_to_hass()
    mock_channel.register_callback.assert_called_once_with(
        callback_attribute="state",
        callback=entity.async_write_ha_state,
    )

    # Test callback removal
    await entity.async_will_remove_from_hass()
    mock_channel.remove_callback.assert_called_once_with(
        callback_attribute="state",
        callback=entity.async_write_ha_state,
    )


async def test_binary_sensor_entity_state_changes(hass: HomeAssistant) -> None:
    """Test binary sensor entity reflects channel state changes."""
    mock_channel = MagicMock(spec=WindowDoorSensor)
    mock_channel.channel_name = "Dynamic Window"
    mock_channel.channel_id = "ch0004"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.state = False

    entity = FreeAtHomeBinarySensorEntity(
        channel=mock_channel,
        value_attribute="state",
        entity_description_kwargs={
            "key": "WindowDoorSensorOnOff",
            "device_class": BinarySensorDeviceClass.WINDOW,
            "translation_key": "window_door",
        },
        sysap_serial_number="TEST123456",
        create_subdevices=False,
    )

    # Initial state
    assert entity.is_on is False

    # Change channel state
    mock_channel.state = True
    assert entity.is_on is True

    # Change back
    mock_channel.state = False
    assert entity.is_on is False


async def test_binary_sensor_filters_none_values(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test that sensors with None values are not created."""
    mock_config_entry.add_to_hass(hass)

    # Create channels with None state
    mock_channel_with_state = MagicMock()
    mock_channel_with_state.state = True

    mock_channel_without_state = MagicMock()
    mock_channel_without_state.state = None

    mock_free_at_home = MagicMock()

    def get_channels_by_class_side_effect(channel_class):
        """Return channels only for WindowDoorSensor."""
        if channel_class.__name__ == "WindowDoorSensor":
            return [mock_channel_with_state, mock_channel_without_state]
        return []

    mock_free_at_home.get_channels_by_class.side_effect = (
        get_channels_by_class_side_effect
    )
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    entities_added = []

    def capture_entities(entity_generator):
        """Capture entities from generator."""
        entities = list(entity_generator)
        entities_added.extend(entities)

    async_add_entities = MagicMock(side_effect=capture_entities)
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # Should have added only 1 entity (the one with state != None)
    assert len(entities_added) == 1


async def test_binary_sensor_entity_description(hass: HomeAssistant) -> None:
    """Test binary sensor entity description attributes."""
    mock_channel = MagicMock(spec=WindowDoorSensor)
    mock_channel.channel_name = "Main Door"
    mock_channel.channel_id = "ch0005"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.state = True

    entity = FreeAtHomeBinarySensorEntity(
        channel=mock_channel,
        value_attribute="state",
        entity_description_kwargs={
            "key": "WindowDoorSensorOnOff",
            "device_class": BinarySensorDeviceClass.WINDOW,
            "translation_key": "window_door",
        },
        sysap_serial_number="TEST123456",
        create_subdevices=False,
    )

    assert entity.entity_description.key == "WindowDoorSensorOnOff"
    assert entity.entity_description.device_class == BinarySensorDeviceClass.WINDOW
    assert entity.entity_description.translation_key == "window_door"
    assert entity.entity_description.has_entity_name is True
    assert entity.entity_description.name == "Main Door"
    assert entity.entity_description.translation_placeholders == {
        "channel_id": "ch0005"
    }


async def test_binary_sensor_translation_key_with_attr(hass: HomeAssistant) -> None:
    """Test translation_key property with _attr_translation_key."""
    mock_channel = MagicMock(spec=WindowDoorSensor)
    mock_channel.channel_name = "Test Window"
    mock_channel.channel_id = "ch0006"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.state = False

    entity = FreeAtHomeBinarySensorEntity(
        channel=mock_channel,
        value_attribute="state",
        entity_description_kwargs={
            "key": "WindowDoorSensorOnOff",
            "device_class": BinarySensorDeviceClass.WINDOW,
            "translation_key": "window_door",
        },
        sysap_serial_number="TEST123456",
        create_subdevices=False,
    )

    # Set _attr_translation_key to test that code path
    entity._attr_translation_key = "custom_translation"

    # The entity_description.translation_key should still take precedence
    assert entity.translation_key == "window_door"

    # But if we delete the entity_description, _attr_translation_key should be used
    entity_description_backup = entity.entity_description
    delattr(entity, "entity_description")
    assert entity.translation_key == "custom_translation"

    # Restore for cleanup
    entity.entity_description = entity_description_backup
