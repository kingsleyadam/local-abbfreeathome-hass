"""Test ABB-free@home cover."""

from unittest.mock import AsyncMock, MagicMock

from abbfreeathome.channels.cover_actuator import (
    AtticWindowActuator,
    AwningActuator,
    BlindActuator,
    ShutterActuator,
)
import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.cover import (
    FreeAtHomeCoverEntity,
    async_setup_entry,
)
from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant


def _build_entity(channel, key="ShutterActuator", create_subdevices=False):
    """Build a cover entity for the given mock channel."""
    return FreeAtHomeCoverEntity(
        channel=channel,
        entity_description_kwargs={
            "key": key,
            "device_class": CoverDeviceClass.BLIND,
        },
        sysap_serial_number="TEST123456",
        create_subdevices=create_subdevices,
    )


async def test_async_setup_entry_no_covers(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup with no cover entities."""
    mock_config_entry.add_to_hass(hass)

    mock_free_at_home = MagicMock()
    mock_free_at_home.get_channels_by_class.return_value = []
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    async_add_entities = MagicMock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # Should be called 4 times (once per cover description)
    assert async_add_entities.call_count == 4


async def test_async_setup_entry_with_covers(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup creates an entity for each cover channel class."""
    mock_config_entry.add_to_hass(hass)

    channels = {}
    for cover_class in (
        AtticWindowActuator,
        AwningActuator,
        BlindActuator,
        ShutterActuator,
    ):
        mock_channel = MagicMock(spec=cover_class)
        mock_channel.channel_name = cover_class.__name__
        mock_channel.channel_id = "ch0000"
        mock_channel.device_serial = "ABB7F57FFFE12345"
        mock_channel.device.is_multi_device = False
        channels[cover_class] = mock_channel

    mock_free_at_home = MagicMock()

    def get_channels_by_class_side_effect(channel_class):
        """Return the mock channel for the requested cover class."""
        return [channels[channel_class]]

    mock_free_at_home.get_channels_by_class.side_effect = (
        get_channels_by_class_side_effect
    )
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    entities_added = []

    def capture_entities(entity_generator):
        """Capture entities from generator."""
        entities_added.extend(list(entity_generator))

    async_add_entities = MagicMock(side_effect=capture_entities)
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert len(entities_added) == 4
    keys = {e.entity_description.key for e in entities_added}
    assert keys == {
        "AtticWindowActuator",
        "AwningActuator",
        "BlindActuator",
        "ShutterActuator",
    }


async def test_cover_entity_properties(hass: HomeAssistant) -> None:
    """Test basic cover entity properties without tilt."""
    mock_channel = MagicMock(spec=BlindActuator)
    mock_channel.channel_name = "Living Room Blind"
    mock_channel.channel_id = "ch0001"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.position = 30
    mock_channel.is_closed = False
    mock_channel.is_closing = False
    mock_channel.is_opening = True
    mock_channel.device.is_multi_device = False

    entity = _build_entity(mock_channel, key="BlindActuator")

    assert entity.entity_description.name == "Living Room Blind"
    assert entity.entity_description.key == "BlindActuator"
    assert entity.unique_id == "ABB7F57FFFE12345_ch0001_BlindActuator"
    assert entity.should_poll is False
    # position 30 -> HA position abs(30 - 100) = 70
    assert entity.current_cover_position == 70
    assert entity.current_cover_tilt_position is None
    assert entity.is_closed is False
    assert entity.is_closing is False
    assert entity.is_opening is True
    assert entity.supported_features == (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.SET_POSITION
        | CoverEntityFeature.STOP
    )

    device_info = entity.device_info
    assert device_info["identifiers"] == {(DOMAIN, "ABB7F57FFFE12345")}


async def test_cover_entity_state_properties(hass: HomeAssistant) -> None:
    """Test is_closed/is_closing/is_opening delegate to the channel."""
    mock_channel = MagicMock(spec=BlindActuator)
    mock_channel.channel_name = "Blind"
    mock_channel.channel_id = "ch0002"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.position = 100

    mock_channel.is_closed = True
    mock_channel.is_closing = True
    mock_channel.is_opening = False

    entity = _build_entity(mock_channel, key="BlindActuator")

    assert entity.is_closed is True
    assert entity.is_closing is True
    assert entity.is_opening is False

    # is_closed can be None when the position is unknown
    mock_channel.is_closed = None
    assert entity.is_closed is None


async def test_cover_entity_position_none(hass: HomeAssistant) -> None:
    """Test position property returns None when channel position is None."""
    mock_channel = MagicMock(spec=BlindActuator)
    mock_channel.channel_name = "Blind"
    mock_channel.channel_id = "ch0003"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.position = None

    entity = _build_entity(mock_channel, key="BlindActuator")

    assert entity.current_cover_position is None


async def test_cover_entity_with_tilt(hass: HomeAssistant) -> None:
    """Test cover entity with tilt support (ShutterActuator)."""
    mock_channel = MagicMock(spec=ShutterActuator)
    mock_channel.channel_name = "Bedroom Shutter"
    mock_channel.channel_id = "ch0004"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.position = 40
    mock_channel.tilt_position = 25

    entity = _build_entity(mock_channel, key="ShutterActuator")

    # tilt 25 -> HA tilt abs(25 - 100) = 75
    assert entity.current_cover_tilt_position == 75
    assert entity.supported_features == (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.SET_POSITION
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_TILT_POSITION
    )


async def test_cover_entity_tilt_position_none(hass: HomeAssistant) -> None:
    """Test tilt position returns None when channel tilt_position is None."""
    mock_channel = MagicMock(spec=ShutterActuator)
    mock_channel.channel_name = "Shutter"
    mock_channel.channel_id = "ch0005"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.position = 40
    mock_channel.tilt_position = None

    entity = _build_entity(mock_channel, key="ShutterActuator")

    assert entity.current_cover_tilt_position is None


async def test_cover_entity_with_subdevices(hass: HomeAssistant) -> None:
    """Test cover entity device info with subdevices enabled."""
    mock_channel = MagicMock(spec=BlindActuator)
    mock_channel.channel_name = "Zone Blind"
    mock_channel.channel_id = "ch0006"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.device_name = "Multi Blind"
    mock_channel.room_name = "Zone 1"
    mock_channel.position = 0
    mock_channel.device.is_multi_device = True
    mock_channel.device.device_id = "5678"

    entity = _build_entity(mock_channel, key="BlindActuator", create_subdevices=True)

    device_info = entity.device_info
    assert device_info["identifiers"] == {(DOMAIN, "ABB7F57FFFE12345_ch0006")}
    assert device_info["name"] == "Multi Blind (ch0006)"
    assert device_info["serial_number"] == "ABB7F57FFFE12345_ch0006"
    assert device_info["hw_version"] == "5678 (sub)"
    assert device_info["suggested_area"] == "Zone 1"
    assert device_info["via_device"] == (DOMAIN, "ABB7F57FFFE12345")


async def test_cover_entity_callbacks_without_tilt(hass: HomeAssistant) -> None:
    """Test callback registration/removal for a cover without tilt."""
    mock_channel = MagicMock(spec=BlindActuator)
    mock_channel.channel_name = "Blind"
    mock_channel.channel_id = "ch0007"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.position = 50

    entity = _build_entity(mock_channel, key="BlindActuator")
    entity.async_write_ha_state = MagicMock()

    await entity.async_added_to_hass()
    # state + position callbacks (no tilt)
    assert mock_channel.register_callback.call_count == 2
    registered = {
        c.kwargs["callback_attribute"]
        for c in mock_channel.register_callback.call_args_list
    }
    assert registered == {"state", "position"}

    await entity.async_will_remove_from_hass()
    assert mock_channel.remove_callback.call_count == 2


async def test_cover_entity_callbacks_with_tilt(hass: HomeAssistant) -> None:
    """Test callback registration/removal includes tilt for shutters."""
    mock_channel = MagicMock(spec=ShutterActuator)
    mock_channel.channel_name = "Shutter"
    mock_channel.channel_id = "ch0008"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.position = 50
    mock_channel.tilt_position = 50

    entity = _build_entity(mock_channel, key="ShutterActuator")
    entity.async_write_ha_state = MagicMock()

    await entity.async_added_to_hass()
    # state + position + tilt_position callbacks
    assert mock_channel.register_callback.call_count == 3
    registered = {
        c.kwargs["callback_attribute"]
        for c in mock_channel.register_callback.call_args_list
    }
    assert registered == {"state", "position", "tilt_position"}

    await entity.async_will_remove_from_hass()
    assert mock_channel.remove_callback.call_count == 3


async def test_cover_entity_actions(hass: HomeAssistant) -> None:
    """Test open/close/set_position/stop actions."""
    mock_channel = MagicMock(spec=BlindActuator)
    mock_channel.channel_name = "Blind"
    mock_channel.channel_id = "ch0009"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.position = 50
    mock_channel.open = AsyncMock()
    mock_channel.close = AsyncMock()
    mock_channel.set_position = AsyncMock()
    mock_channel.stop = AsyncMock()

    entity = _build_entity(mock_channel, key="BlindActuator")

    await entity.async_open_cover()
    mock_channel.open.assert_called_once()

    await entity.async_close_cover()
    mock_channel.close.assert_called_once()

    # HA position 30 -> channel position abs(30 - 100) = 70
    await entity.async_set_cover_position(**{ATTR_POSITION: 30})
    mock_channel.set_position.assert_called_once_with(70)

    await entity.async_stop_cover()
    mock_channel.stop.assert_called_once()


async def test_cover_entity_set_tilt_position(hass: HomeAssistant) -> None:
    """Test set tilt position action inverts the value."""
    mock_channel = MagicMock(spec=ShutterActuator)
    mock_channel.channel_name = "Shutter"
    mock_channel.channel_id = "ch0010"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.position = 50
    mock_channel.tilt_position = 50
    mock_channel.set_tilt_position = AsyncMock()

    entity = _build_entity(mock_channel, key="ShutterActuator")

    # HA tilt 20 -> channel tilt abs(20 - 100) = 80
    await entity.async_set_cover_tilt_position(**{ATTR_TILT_POSITION: 20})
    mock_channel.set_tilt_position.assert_called_once_with(80)


@pytest.mark.parametrize(
    ("position", "expected"),
    [(0, 100), (100, 0), (60, 40)],
)
async def test_cover_entity_position_conversion(
    hass: HomeAssistant, position, expected
) -> None:
    """Test position conversion between channel and HA conventions."""
    mock_channel = MagicMock(spec=BlindActuator)
    mock_channel.channel_name = "Blind"
    mock_channel.channel_id = "ch0011"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.position = position

    entity = _build_entity(mock_channel, key="BlindActuator")

    assert entity.current_cover_position == expected
