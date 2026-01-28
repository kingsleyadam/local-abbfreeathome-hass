"""Test for light platform."""

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.light import (
    FreeAtHomeLightEntity,
    async_setup_entry,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
)
from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_simple_light_channel():
    """Create a mock simple brightness-only light channel."""
    # Use spec to prevent Mock from creating arbitrary attributes
    channel = Mock(
        spec=[
            "device_id",
            "device_serial",
            "channel_id",
            "channel_name",
            "room_name",
            "device_name",
            "device",
            "state",
            "brightness",
            "turn_on",
            "turn_off",
            "set_brightness",
            "refresh_state",
            "register_callback",
            "remove_callback",
        ]
    )
    channel.device_id = "ABB700000001"
    channel.device_serial = "ABB700000001"
    channel.channel_id = "ch0000"
    channel.channel_name = "Simple Light"
    channel.room_name = "Living Room"
    channel.device_name = "Light Device"

    # Mock device
    device = Mock()
    device.is_multi_device = False
    device.device_id = "ABB700000001"
    channel.device = device

    # Simple brightness light (no color temp)
    channel.state = True
    channel.brightness = 50

    channel.turn_on = AsyncMock()
    channel.turn_off = AsyncMock()
    channel.set_brightness = AsyncMock()
    channel.refresh_state = AsyncMock()
    channel.register_callback = Mock()
    channel.remove_callback = Mock()

    return channel


@pytest.fixture
def mock_color_temp_light_channel():
    """Create a mock color temperature light channel."""
    channel = Mock()
    channel.device_id = "ABB700000003"
    channel.device_serial = "ABB700000003"
    channel.channel_id = "ch0000"
    channel.channel_name = "Color Temp Light"
    channel.room_name = "Kitchen"
    channel.device_name = "Color Light Device"

    # Mock device
    device = Mock()
    device.is_multi_device = False
    device.device_id = "ABB700000003"
    channel.device = device

    # Color temperature light
    channel.state = True
    channel.brightness = 80
    channel.color_temperature = 50  # 0-100 range
    channel.color_temperature_warmest = 2700
    channel.color_temperature_coolest = 6500

    channel.turn_on = AsyncMock()
    channel.turn_off = AsyncMock()
    channel.set_brightness = AsyncMock()
    channel.set_color_temperature = AsyncMock()
    channel.refresh_state = AsyncMock()
    channel.register_callback = Mock()
    channel.remove_callback = Mock()

    return channel


@pytest.fixture
def mock_unavailable_light_channel():
    """Create a mock unavailable light channel."""
    channel = Mock()
    channel.device_id = "ABB700000004"
    channel.device_serial = "ABB700000004"
    channel.channel_id = "ch0000"
    channel.channel_name = "Unavailable Light"
    channel.room_name = "Garage"
    channel.device_name = "Unavailable Device"

    # Mock device
    device = Mock()
    device.is_multi_device = False
    device.device_id = "ABB700000004"
    channel.device = device

    channel.state = None
    channel.brightness = None

    channel.turn_on = AsyncMock()
    channel.turn_off = AsyncMock()
    channel.set_brightness = AsyncMock()
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
    """Test setup entry with no light devices."""
    mock_free_at_home.get_channels_by_class.return_value = []

    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    async_add_entities = Mock()

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # Should be called twice (once for DimmingActuator, once for ColorTemperatureActuator)
    assert async_add_entities.call_count == 2


async def test_async_setup_entry_with_devices(
    hass: HomeAssistant,
    mock_config_entry,
    mock_free_at_home,
    mock_simple_light_channel,
):
    """Test setup entry with light devices."""
    mock_free_at_home.get_channels_by_class.return_value = [mock_simple_light_channel]

    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    async_add_entities = Mock()

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # Should be called twice (once for each actuator class)
    assert async_add_entities.call_count == 2


async def test_simple_light_is_on(mock_simple_light_channel):
    """Test is_on property for simple light."""
    entity = FreeAtHomeLightEntity(
        mock_simple_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    mock_simple_light_channel.state = True
    assert entity.is_on is True

    mock_simple_light_channel.state = False
    assert entity.is_on is False


async def test_simple_light_is_unavailable(mock_unavailable_light_channel):
    """Test unavailable light state."""
    entity = FreeAtHomeLightEntity(
        mock_unavailable_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )
    assert entity.is_on is None


async def test_brightness_property(mock_simple_light_channel):
    """Test brightness property for light."""
    entity = FreeAtHomeLightEntity(
        mock_simple_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    # brightness=50 in 0-100 scale should map to ~127 in 0-255 scale
    mock_simple_light_channel.brightness = 50
    assert entity.brightness is not None
    assert 120 <= entity.brightness <= 135  # Allow some tolerance for mapping


async def test_brightness_min_max(mock_simple_light_channel):
    """Test brightness property with min and max values."""
    entity = FreeAtHomeLightEntity(
        mock_simple_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    mock_simple_light_channel.brightness = 1
    assert entity.brightness > 0

    mock_simple_light_channel.brightness = 100
    assert entity.brightness == 255


async def test_color_temp_property(mock_color_temp_light_channel):
    """Test color_temp property."""
    entity = FreeAtHomeLightEntity(
        mock_color_temp_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    # 50% in 0-100 range should map to midpoint between 2700-6500K
    mock_color_temp_light_channel.color_temperature = 50
    assert entity.color_temp_kelvin is not None
    # Should be roughly in the middle: (2700 + 6500) / 2 = 4600
    assert 4500 <= entity.color_temp_kelvin <= 4700


async def test_color_temp_property_none(mock_simple_light_channel):
    """Test color_temp property when not supported."""
    entity = FreeAtHomeLightEntity(
        mock_simple_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )
    # Simple channel doesn't have color_temperature attribute, so color_mode should be brightness
    assert entity.color_mode == ColorMode.BRIGHTNESS


async def test_simple_light_color_mode(mock_simple_light_channel):
    """Test color_mode for simple brightness light."""
    entity = FreeAtHomeLightEntity(
        mock_simple_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )
    assert entity.color_mode == ColorMode.BRIGHTNESS


async def test_color_temp_light_color_mode(mock_color_temp_light_channel):
    """Test color_mode for color temperature light."""
    entity = FreeAtHomeLightEntity(
        mock_color_temp_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )
    assert entity.color_mode == ColorMode.COLOR_TEMP


async def test_simple_light_supported_color_modes(mock_simple_light_channel):
    """Test supported_color_modes for simple light."""
    entity = FreeAtHomeLightEntity(
        mock_simple_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )
    assert entity.supported_color_modes == {ColorMode.BRIGHTNESS}


async def test_color_temp_light_supported_color_modes(mock_color_temp_light_channel):
    """Test supported_color_modes for color temp light."""
    entity = FreeAtHomeLightEntity(
        mock_color_temp_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )
    assert entity.supported_color_modes == {ColorMode.COLOR_TEMP}


async def test_async_turn_on_simple_light(
    hass: HomeAssistant, mock_simple_light_channel
):
    """Test turning on a simple light."""
    entity = FreeAtHomeLightEntity(
        mock_simple_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )
    entity.hass = hass

    await entity.async_turn_on()

    mock_simple_light_channel.turn_on.assert_called_once()


async def test_async_turn_on_with_brightness(
    hass: HomeAssistant, mock_simple_light_channel
):
    """Test turning on light with brightness parameter."""
    entity = FreeAtHomeLightEntity(
        mock_simple_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )
    entity.hass = hass

    # Brightness 127 in 0-255 scale should map to ~50 in 0-100 scale
    await entity.async_turn_on(**{ATTR_BRIGHTNESS: 127})

    mock_simple_light_channel.set_brightness.assert_called_once()
    # Check that set_brightness was called with a value near 50
    call_args = mock_simple_light_channel.set_brightness.call_args[0][0]
    assert 45 <= call_args <= 55


async def test_async_turn_on_with_brightness_min(
    hass: HomeAssistant, mock_simple_light_channel
):
    """Test turning on with min brightness."""
    entity = FreeAtHomeLightEntity(
        mock_simple_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )
    entity.hass = hass

    await entity.async_turn_on(**{ATTR_BRIGHTNESS: 1})

    mock_simple_light_channel.set_brightness.assert_called_once()
    call_args = mock_simple_light_channel.set_brightness.call_args[0][0]
    # Brightness 1 in 0-255 scale maps to approximately 0-1 in 1-100 scale
    assert 0 <= call_args <= 1


async def test_async_turn_on_with_brightness_max(
    hass: HomeAssistant, mock_simple_light_channel
):
    """Test turning on with max brightness."""
    entity = FreeAtHomeLightEntity(
        mock_simple_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )
    entity.hass = hass

    await entity.async_turn_on(**{ATTR_BRIGHTNESS: 255})

    mock_simple_light_channel.set_brightness.assert_called_once()
    call_args = mock_simple_light_channel.set_brightness.call_args[0][0]
    assert call_args == 100


async def test_async_turn_on_color_temp_light_with_color_temp(
    hass: HomeAssistant, mock_color_temp_light_channel
):
    """Test turning on color temp light with color temperature."""
    entity = FreeAtHomeLightEntity(
        mock_color_temp_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )
    entity.hass = hass

    # 4600K should map to roughly middle of 0-100 range
    await entity.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: 4600})

    mock_color_temp_light_channel.set_color_temperature.assert_called_once()
    call_args = mock_color_temp_light_channel.set_color_temperature.call_args[0][0]
    # Should be around 50 in 0-100 range
    assert 45 <= call_args <= 55


async def test_async_turn_off_simple_light(
    hass: HomeAssistant, mock_simple_light_channel
):
    """Test turning off a simple light."""
    entity = FreeAtHomeLightEntity(
        mock_simple_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )
    entity.hass = hass

    await entity.async_turn_off()

    mock_simple_light_channel.turn_off.assert_called_once()


async def test_async_turn_off_color_temp_light(
    hass: HomeAssistant, mock_color_temp_light_channel
):
    """Test turning off a color temp light."""
    entity = FreeAtHomeLightEntity(
        mock_color_temp_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )
    entity.hass = hass

    await entity.async_turn_off()

    mock_color_temp_light_channel.turn_off.assert_called_once()


async def test_entity_unique_id(mock_simple_light_channel):
    """Test entity unique_id."""
    entity = FreeAtHomeLightEntity(
        mock_simple_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    assert entity.unique_id == "ABB700000001_ch0000_light"


async def test_entity_name(mock_simple_light_channel):
    """Test entity name."""
    entity = FreeAtHomeLightEntity(
        mock_simple_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    assert entity.entity_description.name == "Simple Light"


async def test_async_update(hass: HomeAssistant, mock_simple_light_channel):
    """Test async_update calls refresh_state."""
    entity = FreeAtHomeLightEntity(
        mock_simple_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )
    entity.hass = hass

    await entity.async_update()

    mock_simple_light_channel.refresh_state.assert_called_once()


async def test_device_info_simple_device(mock_simple_light_channel):
    """Test device_info for simple (non-multi) device."""
    entity = FreeAtHomeLightEntity(
        mock_simple_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    device_info = entity.device_info
    assert (DOMAIN, "ABB700000001") in device_info["identifiers"]


async def test_device_info_with_subdevices(mock_simple_light_channel):
    """Test device_info when create_subdevices is True and device is multi."""
    mock_simple_light_channel.device.is_multi_device = True

    entity = FreeAtHomeLightEntity(
        mock_simple_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=True,
    )

    device_info = entity.device_info
    assert (DOMAIN, "ABB700000001_ch0000") in device_info["identifiers"]
    assert device_info["name"] == "Light Device (ch0000)"
    assert device_info["via_device"] == (DOMAIN, "ABB700000001")


async def test_callbacks_registered(mock_simple_light_channel):
    """Test that callbacks are registered on async_added_to_hass."""
    entity = FreeAtHomeLightEntity(
        mock_simple_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    await entity.async_added_to_hass()

    # Should register callbacks for state and brightness
    assert mock_simple_light_channel.register_callback.call_count >= 2


async def test_callbacks_removed(mock_simple_light_channel):
    """Test that callbacks are removed on async_will_remove_from_hass."""
    entity = FreeAtHomeLightEntity(
        mock_simple_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    await entity.async_will_remove_from_hass()

    # Should remove callbacks for state and brightness
    assert mock_simple_light_channel.remove_callback.call_count >= 2


async def test_color_temp_callbacks_registered(mock_color_temp_light_channel):
    """Test that color_temperature callback is registered for color temp lights."""
    entity = FreeAtHomeLightEntity(
        mock_color_temp_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    await entity.async_added_to_hass()

    # Should register callbacks for state, brightness, and color_temperature
    assert mock_color_temp_light_channel.register_callback.call_count >= 3


async def test_color_temp_callbacks_removed(mock_color_temp_light_channel):
    """Test that color_temperature callback is removed for color temp lights."""
    entity = FreeAtHomeLightEntity(
        mock_color_temp_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    await entity.async_will_remove_from_hass()

    # Should remove callbacks for state, brightness, and color_temperature
    assert mock_color_temp_light_channel.remove_callback.call_count >= 3


async def test_async_turn_on_color_temp_without_attribute(
    hass: HomeAssistant, mock_simple_light_channel
):
    """Test turning on with color temp kwarg on a light without color_temperature support."""
    entity = FreeAtHomeLightEntity(
        mock_simple_light_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )
    entity.hass = hass

    # Try to set color temp on a channel that doesn't support it
    await entity.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: 4000})

    # Since color temp is not supported, the function returns early and doesn't call anything
    mock_simple_light_channel.turn_on.assert_not_called()
    mock_simple_light_channel.set_brightness.assert_not_called()
