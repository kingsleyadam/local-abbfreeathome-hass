"""Test ABB-free@home binary sensor."""

from unittest.mock import MagicMock, patch

from abbfreeathome.channels.window_door_sensor import WindowDoorSensor

from custom_components.abbfreeathome_ci.binary_sensor import (
    FreeAtHomeBinarySensorEntity,
    FreeAtHomeDeviceConnectivityEntity,
    async_setup_entry,
)
from custom_components.abbfreeathome_ci.const import DOMAIN
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant


async def test_async_setup_entry_no_sensors(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup with no binary sensors."""
    mock_config_entry.add_to_hass(hass)

    mock_free_at_home = MagicMock()
    mock_free_at_home.get_channels_by_class.return_value = []
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}
    mock_free_at_home.get_devices.return_value = {}
    mock_config_entry.runtime_data = MagicMock()

    async_add_entities = MagicMock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # 11 sensor descriptions plus the per device connectivity sensor
    assert async_add_entities.call_count == 12


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
    mock_free_at_home.get_devices.return_value = {}
    mock_config_entry.runtime_data = MagicMock()

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
    entity.platform = MagicMock()
    with patch(
        "custom_components.abbfreeathome_ci.binary_sensor.async_get_via_device_kwargs",
        return_value={"via_device_id": "parent_device_id"},
    ) as mock_via_device_kwargs:
        device_info = entity.device_info
    assert device_info["identifiers"] == {(DOMAIN, "ABB7F57FFFE12345_ch0002")}
    assert device_info["name"] == "Multi Window Sensor (ch0002)"
    assert device_info["serial_number"] == "ABB7F57FFFE12345_ch0002"
    assert device_info["hw_version"] == "4800 (sub)"
    assert device_info["suggested_area"] == "Bedroom"
    mock_via_device_kwargs.assert_called_once_with(
        entity.hass, entity.platform.config_entry.entry_id, "ABB7F57FFFE12345"
    )
    assert device_info["via_device_id"] == "parent_device_id"


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
    mock_free_at_home.get_devices.return_value = {}
    mock_config_entry.runtime_data = MagicMock()

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


async def test_connectivity_sensor_created_per_device(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test a connectivity sensor is created for every device with channels."""
    mock_config_entry.add_to_hass(hass)

    device_with_channels = MagicMock()
    device_with_channels.device_serial = "ABB700CF0EFC"
    device_without_channels = MagicMock()
    device_without_channels.device_serial = "FFFF48000009"

    mock_free_at_home = MagicMock()
    mock_free_at_home.get_channels_by_class.return_value = []
    mock_free_at_home.get_devices.return_value = {
        "ABB700CF0EFC": device_with_channels,
        "FFFF48000009": device_without_channels,
    }
    mock_free_at_home.get_channels_by_device.side_effect = lambda serial: (
        ["ch0000"] if serial == "ABB700CF0EFC" else []
    )
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}
    mock_config_entry.runtime_data = MagicMock()

    entities_added = []
    async_add_entities = MagicMock(
        side_effect=lambda generator: entities_added.extend(list(generator))
    )
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    connectivity = [
        entity
        for entity in entities_added
        if isinstance(entity, FreeAtHomeDeviceConnectivityEntity)
    ]
    assert len(connectivity) == 1
    assert connectivity[0].unique_id == "ABB700CF0EFC_connectivity"


def _connectivity_entity(data) -> FreeAtHomeDeviceConnectivityEntity:
    """Build a connectivity entity over a coordinator holding the given data."""
    coordinator = MagicMock()
    coordinator.data = data
    coordinator.last_update_success = True

    device = MagicMock()
    device.device_serial = "ABB700CF0EFC"

    return FreeAtHomeDeviceConnectivityEntity(coordinator, device)


async def test_connectivity_sensor_reports_a_responsive_device() -> None:
    """Test a device answering the SysAP is reported as connected."""
    entity = _connectivity_entity(
        {
            "ABB700CF0EFC": {
                "unresponsive": False,
                "unresponsive_counter": 0,
                "defect": False,
            }
        }
    )

    assert entity.device_class == BinarySensorDeviceClass.CONNECTIVITY
    assert entity.entity_category == EntityCategory.DIAGNOSTIC
    assert entity.available is True
    assert entity.is_on is True
    assert entity.extra_state_attributes == {
        "unresponsive_counter": 0,
        "defect": False,
    }


async def test_connectivity_sensor_reports_an_unresponsive_device() -> None:
    """Test a device that stopped answering, the empty battery case."""
    entity = _connectivity_entity(
        {
            "ABB7F630796A": {
                "unresponsive": False,
                "unresponsive_counter": 0,
                "defect": False,
            },
            "ABB700CF0EFC": {
                "unresponsive": True,
                "unresponsive_counter": 7,
                "defect": True,
            },
        }
    )

    assert entity.is_on is False
    assert entity.extra_state_attributes == {
        "unresponsive_counter": 7,
        "defect": True,
    }


async def test_connectivity_sensor_unavailable_for_an_unknown_device() -> None:
    """Test a device the api no longer reports becomes unavailable."""
    entity = _connectivity_entity({"ABB7F630796A": {"unresponsive": False}})

    assert entity.available is False
    assert entity.is_on is None
    assert entity.extra_state_attributes is None


async def test_connectivity_sensor_handles_a_failed_first_refresh() -> None:
    """Test no coordinator data at all does not raise."""
    entity = _connectivity_entity(None)

    assert entity.available is False
    assert entity.is_on is None
