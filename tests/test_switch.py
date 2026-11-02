"""Test ABB-free@home switch."""

from unittest.mock import MagicMock, call, patch

from abbfreeathome.channels.virtual.virtual_room_temperature_controller import (
    VirtualRoomTemperatureController,
)
import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.switch import (
    SWITCH_DESCRIPTIONS,
    FreeAtHomeSwitchEntity,
    async_setup_entry,
)
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.core import HomeAssistant


def _build_channel(key, value=True, channel_id="ch0000"):
    """Build a mock channel of the class used by the given description key."""
    description = SWITCH_DESCRIPTIONS[key]
    channel = MagicMock(spec=description["channel_class"])
    channel.channel_name = "Channel Name"
    channel.channel_id = channel_id
    channel.device_serial = "ABB7F57FFFE12345"
    channel.device_name = "Device Name"
    channel.room_name = "Living Room"
    channel.device.is_multi_device = False
    setattr(channel, description["value_attribute"], value)
    return channel


def _build_entity(key, channel, create_subdevices=False):
    """Build a switch entity the way async_setup_entry does for the given key."""
    description = SWITCH_DESCRIPTIONS[key]
    return FreeAtHomeSwitchEntity(
        channel=channel,
        value_attribute=description["value_attribute"],
        entity_description_kwargs={"key": key}
        | description["entity_description_kwargs"],
        sysap_serial_number="TEST123456",
        create_subdevices=create_subdevices,
    )


async def _async_setup_entities(hass, config_entry, channels_by_class):
    """Run the switch platform setup and return the added entities."""
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


async def test_async_setup_entry_no_switches(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup with no switch channels."""
    entities = await _async_setup_entities(hass, mock_config_entry, {})

    assert entities == []


async def test_async_setup_entry_with_all_switches(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup creates an entity for every switch description."""
    channels = {}
    for index, (key, description) in enumerate(SWITCH_DESCRIPTIONS.items()):
        # Descriptions sharing a channel class share one channel, as on a real
        # virtual room temperature controller with on/off and eco switches.
        channel = channels.setdefault(
            description["channel_class"],
            _build_channel(key, channel_id=f"ch{index:04d}"),
        )
        setattr(channel, description["value_attribute"], True)

    entities = await _async_setup_entities(
        hass,
        mock_config_entry,
        {channel_class: [channel] for channel_class, channel in channels.items()},
    )

    assert all(isinstance(entity, FreeAtHomeSwitchEntity) for entity in entities)
    assert [entity.entity_description.key for entity in entities] == list(
        SWITCH_DESCRIPTIONS
    )


async def test_async_setup_entry_skips_none_values(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test that switches are not created for attributes that are None."""
    channel = _build_channel("VirtualRoomTemperatureControllerOnOff")
    channel.eco_mode = None

    entities = await _async_setup_entities(
        hass, mock_config_entry, {VirtualRoomTemperatureController: [channel]}
    )

    assert [entity.entity_description.key for entity in entities] == [
        "VirtualRoomTemperatureControllerOnOff"
    ]


# Unique IDs must never change. Switches without a translation key keep the
# legacy "switch" suffix for backward compatibility.
@pytest.mark.parametrize(
    ("key", "unique_id_suffix"),
    [
        ("DimmingSensorLed", "DimmingSensorLed"),
        ("SwitchActuator", "switch"),
        ("MWireSwitchActuator", "switch"),
        ("SwitchSensorLed", "SwitchSensorLed"),
        ("VirtualBrightessSensorAlarm", "VirtualBrightessSensorAlarm"),
        ("VirtualRainSensorAlarm", "VirtualRainSensorAlarm"),
        (
            "VirtualRoomTemperatureControllerOnOff",
            "VirtualRoomTemperatureControllerOnOff",
        ),
        (
            "VirtualRoomTemperatureControllerECOOnOff",
            "VirtualRoomTemperatureControllerECOOnOff",
        ),
        ("VirtualSwitchActuatorOnOff", "switch"),
        ("VirtualWindSensorAlarm", "VirtualWindSensorAlarm"),
        ("VirtualWindowDoorSensorOnOff", "switch"),
        ("VirtualTemperatureSensorAlarm", "VirtualTemperatureSensorAlarm"),
        ("WelcomeIPMuteActuator", "WelcomeIPMuteActuator"),
        ("BlockableMovementDetector", "BlockableMovementDetector"),
    ],
)
async def test_switch_unique_id(key, unique_id_suffix) -> None:
    """Test the unique ID of every switch description."""
    entity = _build_entity(key, _build_channel(key))

    assert entity.unique_id == f"ABB7F57FFFE12345_ch0000_{unique_id_suffix}"


@pytest.mark.parametrize(
    ("key", "turn_on_method", "turn_off_method"),
    [
        ("DimmingSensorLed", "turn_on_led", "turn_off_led"),
        ("SwitchActuator", "turn_on", "turn_off"),
        ("MWireSwitchActuator", "turn_on", "turn_off"),
        ("SwitchSensorLed", "turn_on_led", "turn_off_led"),
        ("VirtualBrightessSensorAlarm", "turn_on", "turn_off"),
        ("VirtualRainSensorAlarm", "turn_on", "turn_off"),
        ("VirtualRoomTemperatureControllerOnOff", "turn_on", "turn_off"),
        (
            "VirtualRoomTemperatureControllerECOOnOff",
            "turn_on_eco_mode",
            "turn_off_eco_mode",
        ),
        ("VirtualSwitchActuatorOnOff", "turn_on", "turn_off"),
        ("VirtualWindSensorAlarm", "turn_on", "turn_off"),
        ("VirtualWindowDoorSensorOnOff", "turn_on", "turn_off"),
        ("VirtualTemperatureSensorAlarm", "turn_on", "turn_off"),
        ("WelcomeIPMuteActuator", "turn_on", "turn_off"),
        ("BlockableMovementDetector", "turn_on_blocked", "turn_off_blocked"),
    ],
)
async def test_switch_turn_on_off(key, turn_on_method, turn_off_method) -> None:
    """Test turning on and off calls the channel method for the attribute."""
    channel = _build_channel(key)
    entity = _build_entity(key, channel)

    await entity.async_turn_on()
    await entity.async_turn_off()

    getattr(channel, turn_on_method).assert_awaited_once_with()
    getattr(channel, turn_off_method).assert_awaited_once_with()
    assert channel.mock_calls == [
        getattr(call, turn_on_method)(),
        getattr(call, turn_off_method)(),
    ]


async def test_switch_entity_properties() -> None:
    """Test switch entity properties."""
    channel = _build_channel("DimmingSensorLed", channel_id="ch0001")
    entity = _build_entity("DimmingSensorLed", channel)

    assert entity.entity_description.key == "DimmingSensorLed"
    assert entity.entity_description.name == "Channel Name"
    assert entity.entity_description.has_entity_name is True
    assert entity.entity_description.device_class == SwitchDeviceClass.SWITCH
    assert entity.entity_description.translation_placeholders == {
        "channel_id": "ch0001"
    }
    assert entity.translation_key == "sensor_led"
    assert entity.should_poll is False


async def test_switch_translation_key_none() -> None:
    """Test translation_key is None when the description has none."""
    entity = _build_entity("SwitchActuator", _build_channel("SwitchActuator"))

    assert entity.translation_key is None


async def test_switch_translation_key_with_attr() -> None:
    """Test translation_key falls back to _attr_translation_key."""
    entity = _build_entity("DimmingSensorLed", _build_channel("DimmingSensorLed"))
    entity._attr_translation_key = "custom_translation"

    # The entity description takes precedence over _attr_translation_key.
    assert entity.translation_key == "sensor_led"

    del entity.entity_description
    assert entity.translation_key == "custom_translation"


async def test_switch_is_on_follows_channel() -> None:
    """Test is_on reflects the channel's value attribute."""
    channel = _build_channel("BlockableMovementDetector", value=False)
    entity = _build_entity("BlockableMovementDetector", channel)

    assert entity.is_on is False

    channel.blocked = True
    assert entity.is_on is True

    channel.blocked = None
    assert entity.is_on is None


async def test_switch_async_update() -> None:
    """Test updating the switch refreshes the channel state."""
    channel = _build_channel("SwitchActuator")
    entity = _build_entity("SwitchActuator", channel)

    await entity.async_update()

    channel.refresh_state.assert_awaited_once_with()


async def test_switch_entity_callbacks() -> None:
    """Test callbacks are registered and removed for the value attribute."""
    channel = _build_channel("BlockableMovementDetector")
    entity = _build_entity("BlockableMovementDetector", channel)
    entity.async_write_ha_state = MagicMock()

    await entity.async_added_to_hass()
    channel.register_callback.assert_called_once_with(
        callback_attribute="blocked", callback=entity.async_write_ha_state
    )
    channel.device.register_unresponsive_callback.assert_called_once_with(
        entity.async_write_ha_state
    )

    await entity.async_will_remove_from_hass()
    channel.remove_callback.assert_called_once_with(
        callback_attribute="blocked", callback=entity.async_write_ha_state
    )


@pytest.mark.parametrize(
    ("create_subdevices", "is_multi_device"),
    [(False, False), (False, True), (True, False)],
)
async def test_switch_device_info(create_subdevices, is_multi_device) -> None:
    """Test the switch belongs to the main device unless it is a subdevice."""
    channel = _build_channel("SwitchActuator")
    channel.device.is_multi_device = is_multi_device
    entity = _build_entity("SwitchActuator", channel, create_subdevices)

    assert entity.device_info == {"identifiers": {(DOMAIN, "ABB7F57FFFE12345")}}


async def test_switch_device_info_with_subdevices() -> None:
    """Test the switch belongs to a subdevice of a multi-channel device."""
    channel = _build_channel("SwitchActuator", channel_id="ch0002")
    channel.device.is_multi_device = True
    channel.device.device_id = "B002"
    entity = _build_entity("SwitchActuator", channel, create_subdevices=True)
    entity.platform = MagicMock()

    with patch(
        "custom_components.abbfreeathome_ci.switch.async_get_via_device_kwargs",
        return_value={"via_device_id": "parent_device_id"},
    ) as mock_via_device_kwargs:
        device_info = entity.device_info

    mock_via_device_kwargs.assert_called_once_with(
        entity.hass, entity.platform.config_entry.entry_id, "ABB7F57FFFE12345"
    )
    assert device_info["identifiers"] == {(DOMAIN, "ABB7F57FFFE12345_ch0002")}
    assert device_info["name"] == "Device Name (ch0002)"
    assert device_info["serial_number"] == "ABB7F57FFFE12345_ch0002"
    assert device_info["hw_version"] == "B002 (sub)"
    assert device_info["suggested_area"] == "Living Room"
    assert device_info["via_device_id"] == "parent_device_id"
