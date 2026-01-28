"""Test ABB-free@home button."""

from unittest.mock import AsyncMock, MagicMock

from abbfreeathome.channels.trigger import Trigger

from custom_components.abbfreeathome_ci.button import (
    FreeAtHomeButtonEntity,
    async_setup_entry,
)
from custom_components.abbfreeathome_ci.const import DOMAIN
from homeassistant.core import HomeAssistant


async def test_async_setup_entry_no_buttons(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup with no button entities."""
    mock_config_entry.add_to_hass(hass)

    mock_free_at_home = MagicMock()
    mock_free_at_home.get_channels_by_class.return_value = []
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    async_add_entities = MagicMock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    async_add_entities.assert_called_once()
    mock_free_at_home.get_channels_by_class.assert_called_once_with(
        channel_class=Trigger
    )


async def test_async_setup_entry_with_trigger(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup with a trigger button."""
    mock_config_entry.add_to_hass(hass)

    # Create a mock trigger channel
    mock_channel = MagicMock()
    mock_channel.channel_name = "Doorbell"
    mock_channel.channel_id = "ch0000"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.device_name = "Button Device"
    mock_channel.room_name = "Entrance"
    mock_channel.device.is_multi_device = False

    mock_free_at_home = MagicMock()
    mock_free_at_home.get_channels_by_class.return_value = [mock_channel]
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

    assert isinstance(entity, FreeAtHomeButtonEntity)
    assert entity.entity_description.name == "Doorbell"
    assert entity.unique_id == "ABB7F57FFFE12345_ch0000_button"


async def test_button_entity_properties(hass: HomeAssistant) -> None:
    """Test button entity properties."""
    mock_channel = MagicMock(spec=Trigger)
    mock_channel.channel_name = "Test Button"
    mock_channel.channel_id = "ch0001"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.device_name = "Button Device"
    mock_channel.room_name = "Living Room"
    mock_channel.device.is_multi_device = False

    entity = FreeAtHomeButtonEntity(
        channel=mock_channel,
        sysap_serial_number="TEST123456",
        create_subdevices=False,
    )

    assert entity.entity_description.name == "Test Button"
    assert entity.entity_description.key == "button"
    assert entity.unique_id == "ABB7F57FFFE12345_ch0001_button"
    assert entity.should_poll is False

    # Test device info
    device_info = entity.device_info
    assert device_info["identifiers"] == {(DOMAIN, "ABB7F57FFFE12345")}


async def test_button_entity_with_subdevices(hass: HomeAssistant) -> None:
    """Test button entity with subdevices enabled."""
    mock_channel = MagicMock(spec=Trigger)
    mock_channel.channel_name = "Multi Button"
    mock_channel.channel_id = "ch0002"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.device_name = "Multi Button Device"
    mock_channel.room_name = "Bedroom"
    mock_channel.device.is_multi_device = True
    mock_channel.device.device_id = "1234"

    entity = FreeAtHomeButtonEntity(
        channel=mock_channel,
        sysap_serial_number="TEST123456",
        create_subdevices=True,
    )

    # Test device info for subdevice
    device_info = entity.device_info
    assert device_info["identifiers"] == {(DOMAIN, "ABB7F57FFFE12345_ch0002")}
    assert device_info["name"] == "Multi Button Device (ch0002)"
    assert device_info["serial_number"] == "ABB7F57FFFE12345_ch0002"
    assert device_info["hw_version"] == "1234 (sub)"
    assert device_info["suggested_area"] == "Bedroom"
    assert device_info["via_device"] == (DOMAIN, "ABB7F57FFFE12345")


async def test_button_entity_press(hass: HomeAssistant) -> None:
    """Test button entity press action."""
    mock_channel = MagicMock(spec=Trigger)
    mock_channel.channel_name = "Press Button"
    mock_channel.channel_id = "ch0003"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.press = AsyncMock()

    entity = FreeAtHomeButtonEntity(
        channel=mock_channel,
        sysap_serial_number="TEST123456",
        create_subdevices=False,
    )

    # Test pressing the button
    await entity.async_press()
    mock_channel.press.assert_called_once()


async def test_button_entity_multiple_channels(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup with multiple trigger channels."""
    mock_config_entry.add_to_hass(hass)

    # Create multiple mock trigger channels
    mock_channel1 = MagicMock()
    mock_channel1.channel_name = "Button 1"
    mock_channel1.channel_id = "ch0000"
    mock_channel1.device_serial = "ABB7F57FFFE12345"

    mock_channel2 = MagicMock()
    mock_channel2.channel_name = "Button 2"
    mock_channel2.channel_id = "ch0001"
    mock_channel2.device_serial = "ABB7F57FFFE12345"

    mock_channel3 = MagicMock()
    mock_channel3.channel_name = "Button 3"
    mock_channel3.channel_id = "ch0002"
    mock_channel3.device_serial = "ABB7F57FFFE67890"

    mock_free_at_home = MagicMock()
    mock_free_at_home.get_channels_by_class.return_value = [
        mock_channel1,
        mock_channel2,
        mock_channel3,
    ]
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    entities_added = []

    def capture_entities(entity_generator):
        """Capture entities from generator."""
        entities = list(entity_generator)
        entities_added.extend(entities)

    async_add_entities = MagicMock(side_effect=capture_entities)
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # Should have added 3 entities
    assert len(entities_added) == 3
    assert all(isinstance(e, FreeAtHomeButtonEntity) for e in entities_added)

    # Verify unique IDs
    unique_ids = [e.unique_id for e in entities_added]
    assert "ABB7F57FFFE12345_ch0000_button" in unique_ids
    assert "ABB7F57FFFE12345_ch0001_button" in unique_ids
    assert "ABB7F57FFFE67890_ch0002_button" in unique_ids
