"""Test ABB-free@home lock."""

from unittest.mock import MagicMock, patch

from abbfreeathome.channels.des_door_opener_actuator import DesDoorOpenerActuator
import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.lock import (
    FreeAtHomeLockEntity,
    async_setup_entry,
)
from homeassistant.core import HomeAssistant


def _build_channel(channel_id="ch0000", state=False):
    """Build a mock door opener channel."""
    channel = MagicMock(spec=DesDoorOpenerActuator)
    channel.channel_name = "Front Door"
    channel.channel_id = channel_id
    channel.device_serial = "ABB7F57FFFE12345"
    channel.device_name = "Door Opener"
    channel.room_name = "Entrance"
    channel.state = state
    channel.device.is_multi_device = False
    return channel


def _build_entity(channel, create_subdevices=False):
    """Build a lock entity for the given mock channel."""
    return FreeAtHomeLockEntity(
        channel,
        sysap_serial_number="TEST123456",
        create_subdevices=create_subdevices,
    )


async def _async_setup_entities(hass, config_entry, channels):
    """Run the lock platform setup and return the added entities."""
    config_entry.add_to_hass(hass)

    mock_free_at_home = MagicMock()
    mock_free_at_home.get_channels_by_class.return_value = channels
    hass.data[DOMAIN] = {config_entry.entry_id: mock_free_at_home}

    entities_added = []

    def capture_entities(entity_generator):
        """Capture entities from generator."""
        entities_added.extend(list(entity_generator))

    async_add_entities = MagicMock(side_effect=capture_entities)
    await async_setup_entry(hass, config_entry, async_add_entities)

    mock_free_at_home.get_channels_by_class.assert_called_once_with(
        channel_class=DesDoorOpenerActuator
    )
    assert async_add_entities.call_count == 1
    return entities_added


async def test_async_setup_entry_no_locks(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup with no door opener channels."""
    entities = await _async_setup_entities(hass, mock_config_entry, [])

    assert entities == []


async def test_async_setup_entry_with_door_openers(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup creates a lock for each door opener channel."""
    entities = await _async_setup_entities(
        hass,
        mock_config_entry,
        [_build_channel("ch0000"), _build_channel("ch0001")],
    )

    assert all(isinstance(entity, FreeAtHomeLockEntity) for entity in entities)
    assert [entity.unique_id for entity in entities] == [
        "ABB7F57FFFE12345_ch0000_valve",
        "ABB7F57FFFE12345_ch0001_valve",
    ]


async def test_lock_entity_properties() -> None:
    """Test lock entity properties."""
    entity = _build_entity(_build_channel())

    assert entity.entity_description.key == "DesDoorOpenerActuatorLock"
    assert entity.entity_description.name == "Front Door"
    # The "valve" suffix is legacy and must not change, so existing lock
    # entities keep their unique ID.
    assert entity.unique_id == "ABB7F57FFFE12345_ch0000_valve"
    assert entity.should_poll is False


@pytest.mark.parametrize(
    ("state", "is_locked"),
    [(False, True), (True, False), (None, None)],
)
async def test_lock_is_locked(state, is_locked) -> None:
    """Test the door is locked while the door opener is off, unknown without state."""
    entity = _build_entity(_build_channel(state=state))

    assert entity.is_locked is is_locked


async def test_lock_lock_unlock() -> None:
    """Test locking and unlocking call the channel."""
    channel = _build_channel()
    entity = _build_entity(channel)

    await entity.async_lock()
    channel.lock.assert_awaited_once_with()
    channel.unlock.assert_not_awaited()

    await entity.async_unlock()
    channel.unlock.assert_awaited_once_with()


async def test_lock_async_update() -> None:
    """Test updating the lock refreshes the channel state."""
    channel = _build_channel()
    entity = _build_entity(channel)

    await entity.async_update()

    channel.refresh_state.assert_awaited_once_with()


async def test_lock_entity_callbacks() -> None:
    """Test callbacks are registered and removed for the state attribute."""
    channel = _build_channel()
    entity = _build_entity(channel)
    entity.async_write_ha_state = MagicMock()

    await entity.async_added_to_hass()
    channel.register_callback.assert_called_once_with(
        callback_attribute="state", callback=entity.async_write_ha_state
    )
    channel.device.register_unresponsive_callback.assert_called_once_with(
        entity.async_write_ha_state
    )

    await entity.async_will_remove_from_hass()
    channel.remove_callback.assert_called_once_with(
        callback_attribute="state", callback=entity.async_write_ha_state
    )


@pytest.mark.parametrize(
    ("create_subdevices", "is_multi_device"),
    [(False, False), (False, True), (True, False)],
)
async def test_lock_device_info(create_subdevices, is_multi_device) -> None:
    """Test the lock belongs to the main device unless it is a subdevice."""
    channel = _build_channel()
    channel.device.is_multi_device = is_multi_device
    entity = _build_entity(channel, create_subdevices)

    assert entity.device_info == {"identifiers": {(DOMAIN, "ABB7F57FFFE12345")}}


async def test_lock_device_info_with_subdevices() -> None:
    """Test the lock belongs to a subdevice of a multi-channel device."""
    channel = _build_channel("ch0002")
    channel.device.is_multi_device = True
    channel.device.device_id = "B008"
    entity = _build_entity(channel, create_subdevices=True)
    entity.platform = MagicMock()

    with patch(
        "custom_components.abbfreeathome_ci.lock.async_get_sub_device_info"
    ) as mock_sub_device_info:
        device_info = entity.device_info

    mock_sub_device_info.assert_called_once_with(
        entity.hass, entity.platform.config_entry.entry_id, channel
    )
    assert device_info is mock_sub_device_info.return_value
