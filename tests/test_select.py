"""Test ABB-free@home select."""

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.select import (
    SELECT_DESCRIPTIONS,
    FreeAtHomeSelectEntity,
    async_setup_entry,
)
from homeassistant.core import HomeAssistant

STRINGS_PATH = Path("custom_components/abbfreeathome_ci/strings.json")


def _build_channel(key, forced_position="deactivated", channel_id="ch0000"):
    """Build a mock channel of the class used by the given description key."""
    description = SELECT_DESCRIPTIONS[key]
    channel = MagicMock(spec=description["channel_class"])
    channel.channel_name = "Channel Name"
    channel.channel_id = channel_id
    channel.device_serial = "ABB7F57FFFE12345"
    channel.device_name = "Device Name"
    channel.room_name = "Living Room"
    channel.device.is_multi_device = False
    setattr(channel, description["current_option_attribute"], forced_position)
    return channel


def _build_entity(key, channel, create_subdevices=False):
    """Build a select entity the way async_setup_entry does for the given key."""
    description = SELECT_DESCRIPTIONS[key]
    return FreeAtHomeSelectEntity(
        channel,
        entity_description_kwargs={"key": key}
        | description["entity_description_kwargs"],
        current_option_attribute=description["current_option_attribute"],
        select_option_method=description["select_option_method"],
        sysap_serial_number="TEST123456",
        create_subdevices=create_subdevices,
    )


async def _async_setup_entities(hass, config_entry, channels_by_class):
    """Run the select platform setup and return the added entities."""
    config_entry.add_to_hass(hass)

    mock_free_at_home = MagicMock()

    def get_channels_by_class_side_effect(channel_class):
        """Return the mock channels for the requested channel class."""
        return channels_by_class.get(channel_class, [])

    mock_free_at_home.get_channels_by_class.side_effect = (
        get_channels_by_class_side_effect
    )
    hass.data[DOMAIN] = {config_entry.entry_id: mock_free_at_home}

    entities_added = []

    def capture_entities(entity_generator):
        """Capture entities from generator."""
        entities_added.extend(list(entity_generator))

    async_add_entities = MagicMock(side_effect=capture_entities)
    await async_setup_entry(hass, config_entry, async_add_entities)

    assert async_add_entities.call_count == 1
    return entities_added


async def test_async_setup_entry_no_selects(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup with no forced position channels."""
    entities = await _async_setup_entities(hass, mock_config_entry, {})

    assert entities == []


async def test_async_setup_entry_with_all_selects(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup creates a select for every select description."""
    entities = await _async_setup_entities(
        hass,
        mock_config_entry,
        {
            description["channel_class"]: [_build_channel(key)]
            for key, description in SELECT_DESCRIPTIONS.items()
        },
    )

    assert all(isinstance(entity, FreeAtHomeSelectEntity) for entity in entities)
    # Unique IDs must never change, so the expected keys are listed explicitly.
    assert [entity.unique_id for entity in entities] == [
        "ABB7F57FFFE12345_ch0000_AtticWindowActuatorForcedPosition",
        "ABB7F57FFFE12345_ch0000_AwningActuatorForcedPosition",
        "ABB7F57FFFE12345_ch0000_BlindActuatorForcedPosition",
        "ABB7F57FFFE12345_ch0000_ShutterActuatorForcedPosition",
        "ABB7F57FFFE12345_ch0000_SwitchActuatorForcedPosition",
        "ABB7F57FFFE12345_ch0000_DimmingActuatorForcedPosition",
    ]


@pytest.mark.parametrize("key", SELECT_DESCRIPTIONS)
def test_select_options_are_translated(key) -> None:
    """Test every option has a translated state and unknown is no option.

    The library reports "unknown" while no forced position is known. It must
    not be selectable, so Home Assistant shows the entity state as unknown.
    """
    entity_description_kwargs = SELECT_DESCRIPTIONS[key]["entity_description_kwargs"]
    strings = json.loads(STRINGS_PATH.read_text(encoding="utf-8"))
    translation = strings["entity"]["select"][
        entity_description_kwargs["translation_key"]
    ]

    assert "unknown" not in entity_description_kwargs["options"]
    assert set(entity_description_kwargs["options"]) == set(translation["state"])


async def test_select_entity_properties() -> None:
    """Test select entity properties."""
    channel = _build_channel("SwitchActuatorForcedPosition", channel_id="ch0001")
    entity = _build_entity("SwitchActuatorForcedPosition", channel)

    assert entity.entity_description.key == "SwitchActuatorForcedPosition"
    assert entity.entity_description.name == "Channel Name"
    assert entity.entity_description.has_entity_name is True
    assert entity.entity_description.translation_placeholders == {
        "channel_id": "ch0001",
        "channel_name": "Channel Name",
    }
    assert entity.translation_key == "switch_actuator"
    assert entity.options == ["deactivated", "forced_on", "forced_off"]
    assert entity.should_poll is False


@pytest.mark.parametrize(
    ("forced_position", "state"),
    [
        ("deactivated", "deactivated"),
        ("forced_on", "forced_on"),
        ("forced_off", "forced_off"),
        ("unknown", None),
        (None, None),
    ],
)
async def test_select_current_option(forced_position, state) -> None:
    """Test the state follows the channel's forced position."""
    channel = _build_channel("SwitchActuatorForcedPosition", forced_position)
    entity = _build_entity("SwitchActuatorForcedPosition", channel)

    assert entity.current_option == forced_position
    assert entity.state == state


@pytest.mark.parametrize("key", SELECT_DESCRIPTIONS)
async def test_select_option(key) -> None:
    """Test selecting an option sets the forced position on the channel."""
    channel = _build_channel(key)
    entity = _build_entity(key, channel)

    await entity.async_select_option("deactivated")

    channel.set_forced_position.assert_awaited_once_with("deactivated")
    assert channel.mock_calls == [call.set_forced_position("deactivated")]


async def test_select_entity_callbacks() -> None:
    """Test callbacks are registered and removed for the forced position."""
    channel = _build_channel("BlindActuatorForcedPosition")
    entity = _build_entity("BlindActuatorForcedPosition", channel)
    entity.async_write_ha_state = MagicMock()

    await entity.async_added_to_hass()
    channel.register_callback.assert_called_once_with(
        callback_attribute="forced_position", callback=entity.async_write_ha_state
    )
    channel.device.register_unresponsive_callback.assert_called_once_with(
        entity.async_write_ha_state
    )

    await entity.async_will_remove_from_hass()
    channel.remove_callback.assert_called_once_with(
        callback_attribute="forced_position", callback=entity.async_write_ha_state
    )


@pytest.mark.parametrize(
    ("create_subdevices", "is_multi_device"),
    [(False, False), (False, True), (True, False)],
)
async def test_select_device_info(create_subdevices, is_multi_device) -> None:
    """Test the select belongs to the main device unless it is a subdevice."""
    channel = _build_channel("SwitchActuatorForcedPosition")
    channel.device.is_multi_device = is_multi_device
    entity = _build_entity("SwitchActuatorForcedPosition", channel, create_subdevices)

    assert entity.device_info == {"identifiers": {(DOMAIN, "ABB7F57FFFE12345")}}


async def test_select_device_info_with_subdevices() -> None:
    """Test the select belongs to a subdevice of a multi-channel device."""
    channel = _build_channel("SwitchActuatorForcedPosition", channel_id="ch0002")
    channel.device.is_multi_device = True
    channel.device.device_id = "B002"
    entity = _build_entity(
        "SwitchActuatorForcedPosition", channel, create_subdevices=True
    )
    entity.platform = MagicMock()

    with patch(
        "custom_components.abbfreeathome_ci.select.async_get_sub_device_info"
    ) as mock_sub_device_info:
        device_info = entity.device_info

    mock_sub_device_info.assert_called_once_with(
        entity.hass, entity.platform.config_entry.entry_id, channel
    )
    assert device_info is mock_sub_device_info.return_value
