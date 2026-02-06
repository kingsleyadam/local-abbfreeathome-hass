"""Test for cover platform."""

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.cover import (
    CoverActuatorState,
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


@pytest.fixture
def mock_cover_channel():
    """Create a mock cover channel."""
    channel = Mock()
    channel.device_id = "ABB_COVER"
    channel.device_serial = "ABB_COVER"
    channel.channel_id = "ch0000"
    channel.channel_name = "Cover"
    channel.room_name = "Living Room"
    channel.device_name = "Cover Device"
    channel.device.is_multi_device = False
    channel.device.device_id = "ABB_COVER_DEV"
    channel.position = (
        50  # 50% open (0 is open, 100 is closed in F@H usually? No, check code)
    )
    # Code: current_cover_position -> abs(self._channel.position - 100)
    # So if channel.position is 100 (closed), HA position is 0.
    # If channel.position is 0 (open), HA position is 100.
    channel.state = "idle"
    channel.tilt_position = 50

    channel.open = AsyncMock()
    channel.close = AsyncMock()
    channel.stop = AsyncMock()
    channel.set_position = AsyncMock()
    channel.set_tilt_position = AsyncMock()
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
    """Test setup entry with no cover devices."""
    mock_free_at_home.get_channels_by_class.return_value = []
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}
    async_add_entities = Mock()

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # There are 4 types of actuators in SELECT_DESCRIPTIONS, so called 4 times with empty lists
    assert async_add_entities.call_count == 4
    for call in async_add_entities.call_args_list:
        assert len(list(call[0][0])) == 0


async def test_async_setup_entry_with_devices(
    hass: HomeAssistant,
    mock_config_entry,
    mock_free_at_home,
    mock_cover_channel,
):
    """Test setup entry with cover devices."""
    mock_free_at_home.get_channels_by_class.side_effect = [
        [mock_cover_channel],
        [],
        [],
        [],
    ]
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}
    async_add_entities = Mock()

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert async_add_entities.call_count == 4
    # One of them should have 1 device
    found = False
    for call in async_add_entities.call_args_list:
        if len(list(call[0][0])) == 1:
            found = True
            break
    assert found


async def test_cover_attributes(mock_cover_channel):
    """Test cover attributes."""
    entity = FreeAtHomeCoverEntity(
        mock_cover_channel,
        entity_description_kwargs={
            "key": "test_blind",
            "device_class": CoverDeviceClass.BLIND,
        },
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )

    # channel.position = 50 -> HA position = 50
    mock_cover_channel.position = 50
    assert entity.current_cover_position == 50
    assert not entity.is_closed

    # channel.position = 100 -> HA position = 0 (Closed)
    mock_cover_channel.position = 100
    assert entity.current_cover_position == 0
    assert entity.is_closed

    # channel.position = 0 -> HA position = 100 (Open)
    mock_cover_channel.position = 0
    assert entity.current_cover_position == 100
    assert not entity.is_closed


async def test_cover_tilt(mock_cover_channel):
    """Test cover tilt."""
    entity = FreeAtHomeCoverEntity(
        mock_cover_channel,
        entity_description_kwargs={"key": "test_tilt"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )

    mock_cover_channel.tilt_position = 50
    assert entity.current_cover_tilt_position == 50

    del mock_cover_channel.tilt_position
    assert entity.current_cover_tilt_position is None

    # Re-add for other tests
    mock_cover_channel.tilt_position = 50


async def test_cover_state(mock_cover_channel):
    """Test cover state properties."""
    entity = FreeAtHomeCoverEntity(
        mock_cover_channel,
        entity_description_kwargs={"key": "test_state"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )

    mock_cover_channel.state = CoverActuatorState.closing.name
    assert entity.is_closing
    assert not entity.is_opening

    mock_cover_channel.state = CoverActuatorState.opening.name
    assert not entity.is_closing
    assert entity.is_opening

    mock_cover_channel.state = "idle"
    assert not entity.is_closing
    assert not entity.is_opening


async def test_supported_features(mock_cover_channel):
    """Test supported features."""
    entity = FreeAtHomeCoverEntity(
        mock_cover_channel,
        entity_description_kwargs={"key": "test_features"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )

    features = entity.supported_features
    assert features & CoverEntityFeature.OPEN
    assert features & CoverEntityFeature.CLOSE
    assert features & CoverEntityFeature.SET_POSITION
    assert features & CoverEntityFeature.STOP
    assert features & CoverEntityFeature.SET_TILT_POSITION

    del mock_cover_channel.tilt_position
    features = entity.supported_features
    assert not (features & CoverEntityFeature.SET_TILT_POSITION)


async def test_async_methods(mock_cover_channel):
    """Test async methods."""
    entity = FreeAtHomeCoverEntity(
        mock_cover_channel,
        entity_description_kwargs={"key": "test_async"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )

    await entity.async_open_cover()
    mock_cover_channel.open.assert_called_once()

    await entity.async_close_cover()
    mock_cover_channel.close.assert_called_once()

    await entity.async_stop_cover()
    mock_cover_channel.stop.assert_called_once()

    # HA Position 80 -> F@H Position 20 (abs(80-100))
    await entity.async_set_cover_position(**{ATTR_POSITION: 80})
    mock_cover_channel.set_position.assert_called_once_with(20)

    # HA Tilt 80 -> F@H Tilt 20
    await entity.async_set_cover_tilt_position(**{ATTR_TILT_POSITION: 80})
    mock_cover_channel.set_tilt_position.assert_called_once_with(20)


async def test_callbacks(mock_cover_channel):
    """Test callbacks."""
    entity = FreeAtHomeCoverEntity(
        mock_cover_channel,
        entity_description_kwargs={"key": "test_callbacks"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )

    await entity.async_added_to_hass()
    # 2 standard attributes + tilt
    assert mock_cover_channel.register_callback.call_count == 3

    await entity.async_will_remove_from_hass()
    assert mock_cover_channel.remove_callback.call_count == 3


async def test_callbacks_no_tilt(mock_cover_channel):
    """Test callbacks without tilt."""
    del mock_cover_channel.tilt_position

    entity = FreeAtHomeCoverEntity(
        mock_cover_channel,
        entity_description_kwargs={"key": "test_callbacks"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )

    await entity.async_added_to_hass()
    # 2 standard attributes only
    assert mock_cover_channel.register_callback.call_count == 2

    await entity.async_will_remove_from_hass()
    assert mock_cover_channel.remove_callback.call_count == 2


async def test_device_info(mock_cover_channel):
    """Test device info."""
    entity = FreeAtHomeCoverEntity(
        mock_cover_channel,
        entity_description_kwargs={"key": "test_device_info"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )
    assert entity.device_info["identifiers"] == {(DOMAIN, "ABB_COVER")}

    mock_cover_channel.device.is_multi_device = True
    entity = FreeAtHomeCoverEntity(
        mock_cover_channel,
        entity_description_kwargs={"key": "test_device_info_sub"},
        sysap_serial_number="SERIAL",
        create_subdevices=True,
    )
    assert entity.device_info["identifiers"] == {(DOMAIN, "ABB_COVER_ch0000")}


async def test_unique_id(mock_cover_channel):
    """Test unique id."""
    entity = FreeAtHomeCoverEntity(
        mock_cover_channel,
        entity_description_kwargs={"key": "MyKey"},
        sysap_serial_number="SERIAL",
        create_subdevices=False,
    )
    assert entity.unique_id == "ABB_COVER_ch0000_MyKey"
