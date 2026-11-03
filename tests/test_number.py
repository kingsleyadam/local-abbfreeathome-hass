"""Test ABB-free@home number."""

from unittest.mock import MagicMock, call, patch

from abbfreeathome.channels.virtual.virtual_wind_sensor import VirtualWindSensor
import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.number import (
    NUMBER_DESCRIPTIONS,
    FreeAtHomeNumberEntity,
    async_setup_entry,
)
from homeassistant.components.number import NumberDeviceClass
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant


def _build_channel(key, value=21.5, channel_id="ch0000"):
    """Build a mock channel of the class used by the given description key."""
    description = NUMBER_DESCRIPTIONS[key]
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
    """Build a number entity the way async_setup_entry does for the given key."""
    description = NUMBER_DESCRIPTIONS[key]
    return FreeAtHomeNumberEntity(
        channel,
        value_attribute=description["value_attribute"],
        entity_description_kwargs={"key": key}
        | description["entity_description_kwargs"],
        sysap_serial_number="TEST123456",
        create_subdevices=create_subdevices,
    )


async def _async_setup_entities(hass, config_entry, channels_by_class):
    """Run the number platform setup and return the added entities."""
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


async def test_async_setup_entry_no_numbers(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup with no number channels."""
    entities = await _async_setup_entities(hass, mock_config_entry, {})

    assert entities == []


async def test_async_setup_entry_with_all_numbers(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup creates an entity for every number description."""
    channels = {}
    for key, description in NUMBER_DESCRIPTIONS.items():
        # Descriptions sharing a channel class share one channel, as on a real
        # virtual device with several values.
        channel = channels.setdefault(description["channel_class"], _build_channel(key))
        setattr(channel, description["value_attribute"], 1.0)

    entities = await _async_setup_entities(
        hass,
        mock_config_entry,
        {channel_class: [channel] for channel_class, channel in channels.items()},
    )

    assert all(isinstance(entity, FreeAtHomeNumberEntity) for entity in entities)
    # Unique IDs must never change, so the expected keys are listed explicitly,
    # including the misspelled "TwoMay" keys.
    assert [entity.unique_id for entity in entities] == [
        f"ABB7F57FFFE12345_ch0000_{key}"
        for key in (
            "VirtualBrightnessSensor",
            "VirtualEnergyBatteryBatteryPower",
            "VirtualEnergyBatterySoc",
            "VirtualEnergyBatteryImportedToday",
            "VirtualEnergyBatteryExportedToday",
            "VirtualEnergyBatteryImportedTotal",
            "VirtualEnergyBatteryExportedTotal",
            "VirtualEnergyInverterCurrentPower",
            "VirtualEnergyInverterImportedToday",
            "VirtualEnergyInverterImportedTotal",
            "VirtualEnergyTwoWayMeterCurrentPower",
            "VirtualEnergyTwoMayMeterImportedToday",
            "VirtualEnergyTwoMayMeterExportedToday",
            "VirtualEnergyTwoMayMeterImportedTotal",
            "VirtualEnergyTwoMayMeterExportedTotal",
            "VirtualRoomTemperatureControllerCurrentTemperature",
            "VirtualRoomTemperatureControllerTargetTemperature",
            "VirtualTemperatureSensor",
            "VirtualWindSensorForce",
            "VirtualWindSensorSpeed",
        )
    ]


async def test_async_setup_entry_skips_none_values(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test that numbers are not created for attributes that are None."""
    channel = _build_channel("VirtualWindSensorForce", value=3)
    channel.speed = None

    entities = await _async_setup_entities(
        hass, mock_config_entry, {VirtualWindSensor: [channel]}
    )

    assert [entity.entity_description.key for entity in entities] == [
        "VirtualWindSensorForce"
    ]


async def test_number_entity_properties() -> None:
    """Test number entity properties."""
    key = "VirtualRoomTemperatureControllerTargetTemperature"
    entity = _build_entity(key, _build_channel(key, channel_id="ch0001"))

    assert entity.entity_description.key == key
    assert entity.entity_description.name == "Channel Name"
    assert entity.entity_description.has_entity_name is True
    assert entity.entity_description.translation_placeholders == {
        "channel_id": "ch0001"
    }
    assert entity.translation_key == "virtual_rtc_target_temperature"
    assert entity.device_class == NumberDeviceClass.TEMPERATURE
    assert entity.native_min_value == 7.0
    assert entity.native_max_value == 35.0
    assert entity.native_step == 0.5
    assert entity.native_unit_of_measurement == UnitOfTemperature.CELSIUS
    assert entity.should_poll is False


async def test_number_native_value_follows_channel() -> None:
    """Test native_value reflects the channel's value attribute."""
    channel = _build_channel("VirtualWindSensorSpeed", value=4.2)
    entity = _build_entity("VirtualWindSensorSpeed", channel)

    assert entity.native_value == 4.2

    channel.speed = 7.5
    assert entity.native_value == 7.5

    channel.speed = None
    assert entity.native_value is None


@pytest.mark.parametrize("key", NUMBER_DESCRIPTIONS)
async def test_number_set_native_value(key) -> None:
    """Test setting a value calls the channel setter for the attribute."""
    setter = f"set_{NUMBER_DESCRIPTIONS[key]['value_attribute']}"
    channel = _build_channel(key)
    entity = _build_entity(key, channel)

    await entity.async_set_native_value(5)

    getattr(channel, setter).assert_awaited_once_with(5.0)
    assert isinstance(getattr(channel, setter).await_args.args[0], float)
    assert channel.mock_calls == [getattr(call, setter)(5.0)]


async def test_number_async_update() -> None:
    """Test updating the number refreshes the channel state."""
    channel = _build_channel("VirtualTemperatureSensor")
    entity = _build_entity("VirtualTemperatureSensor", channel)

    await entity.async_update()

    channel.refresh_state.assert_awaited_once_with()


async def test_number_entity_callbacks() -> None:
    """Test callbacks are registered and removed for the value attribute."""
    channel = _build_channel("VirtualWindSensorForce")
    entity = _build_entity("VirtualWindSensorForce", channel)
    entity.async_write_ha_state = MagicMock()

    await entity.async_added_to_hass()
    channel.register_callback.assert_called_once_with(
        callback_attribute="force", callback=entity.async_write_ha_state
    )
    channel.device.register_unresponsive_callback.assert_called_once_with(
        entity.async_write_ha_state
    )

    await entity.async_will_remove_from_hass()
    channel.remove_callback.assert_called_once_with(
        callback_attribute="force", callback=entity.async_write_ha_state
    )


@pytest.mark.parametrize(
    ("create_subdevices", "is_multi_device"),
    [(False, False), (False, True), (True, False)],
)
async def test_number_device_info(create_subdevices, is_multi_device) -> None:
    """Test the number belongs to the main device unless it is a subdevice."""
    channel = _build_channel("VirtualTemperatureSensor")
    channel.device.is_multi_device = is_multi_device
    entity = _build_entity("VirtualTemperatureSensor", channel, create_subdevices)

    assert entity.device_info == {"identifiers": {(DOMAIN, "ABB7F57FFFE12345")}}


async def test_number_device_info_with_subdevices() -> None:
    """Test the number belongs to a subdevice of a multi-channel device."""
    channel = _build_channel("VirtualTemperatureSensor", channel_id="ch0002")
    channel.device.is_multi_device = True
    channel.device.device_id = "6000"
    entity = _build_entity("VirtualTemperatureSensor", channel, create_subdevices=True)
    entity.platform = MagicMock()

    with patch(
        "custom_components.abbfreeathome_ci.number.async_get_sub_device_info"
    ) as mock_sub_device_info:
        device_info = entity.device_info

    mock_sub_device_info.assert_called_once_with(
        entity.hass, entity.platform.config_entry.entry_id, channel
    )
    assert device_info is mock_sub_device_info.return_value
