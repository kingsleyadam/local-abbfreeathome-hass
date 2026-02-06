"""Test for climate platform."""

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.abbfreeathome_ci.climate import (
    FreeAtHomeClimateEntity,
    async_setup_entry,
)
from custom_components.abbfreeathome_ci.const import DOMAIN
from homeassistant.components.climate import ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_climate_channel():
    """Create a mock climate channel."""
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
            "current_temperature",
            "heating",
            "cooling",
            "target_temperature",
            "eco_mode",
            "turn_on",
            "turn_off",
            "set_temperature",
            "eco_on",
            "eco_off",
            "refresh_state",
            "register_callback",
            "remove_callback",
        ]
    )
    channel.device_id = "ABB700000001"
    channel.device_serial = "ABB700000001"
    channel.channel_id = "ch0000"
    channel.channel_name = "Climate Control"
    channel.room_name = "Living Room"
    channel.device_name = "Thermostat"

    # Mock device
    device = Mock()
    device.is_multi_device = False
    device.device_id = "ABB700000001"
    channel.device = device

    # Initial state
    channel.state = True
    channel.current_temperature = 21.5
    channel.heating = 0
    channel.cooling = 0
    channel.target_temperature = 22.0
    channel.eco_mode = False

    channel.turn_on = AsyncMock()
    channel.turn_off = AsyncMock()
    channel.set_temperature = AsyncMock()
    channel.eco_on = AsyncMock()
    channel.eco_off = AsyncMock()
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
    """Test setup entry with no climate devices."""
    mock_free_at_home.get_channels_by_class.return_value = []

    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    async_add_entities = Mock()

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    async_add_entities.assert_called_once()
    assert len(list(async_add_entities.call_args[0][0])) == 0


async def test_async_setup_entry_with_devices(
    hass: HomeAssistant,
    mock_config_entry,
    mock_free_at_home,
    mock_climate_channel,
):
    """Test setup entry with climate devices."""
    mock_free_at_home.get_channels_by_class.return_value = [mock_climate_channel]

    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    async_add_entities = Mock()

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    async_add_entities.assert_called_once()
    assert len(list(async_add_entities.call_args[0][0])) == 1


async def test_unique_id(mock_climate_channel):
    """Test entity unique_id."""
    entity = FreeAtHomeClimateEntity(
        mock_climate_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    assert entity.unique_id == "ABB700000001_ch0000_climate"


async def test_device_info_simple_device(mock_climate_channel):
    """Test device_info for simple (non-multi) device."""
    entity = FreeAtHomeClimateEntity(
        mock_climate_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    device_info = entity.device_info
    assert (DOMAIN, "ABB700000001") in device_info["identifiers"]


async def test_device_info_with_subdevices(mock_climate_channel):
    """Test device_info when create_subdevices is True and device is multi."""
    mock_climate_channel.device.is_multi_device = True

    entity = FreeAtHomeClimateEntity(
        mock_climate_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=True,
    )

    device_info = entity.device_info
    assert (DOMAIN, "ABB700000001_ch0000") in device_info["identifiers"]
    assert device_info["name"] == "Thermostat (ch0000)"
    assert device_info["via_device"] == (DOMAIN, "ABB700000001")


async def test_properties_basics(mock_climate_channel):
    """Test basic properties."""
    entity = FreeAtHomeClimateEntity(
        mock_climate_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    assert entity.temperature_unit == UnitOfTemperature.CELSIUS
    assert entity.target_temperature_step == 0.5
    assert entity.max_temp == 35.0
    assert entity.min_temp == 7.0
    assert entity.hvac_modes == [HVACMode.HEAT_COOL, HVACMode.OFF]
    assert entity.preset_modes == ["none", "eco"]
    assert entity.supported_features == (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )


async def test_extra_state_attributes(mock_climate_channel):
    """Test extra state attributes."""
    entity = FreeAtHomeClimateEntity(
        mock_climate_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )
    mock_climate_channel.heating = 1
    mock_climate_channel.cooling = 0
    assert entity.extra_state_attributes == {"heating": 1, "cooling": 0}


async def test_current_temperature(mock_climate_channel):
    """Test current temperature property."""
    entity = FreeAtHomeClimateEntity(
        mock_climate_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )
    assert entity.current_temperature == 21.5


async def test_hvac_mode(mock_climate_channel):
    """Test hvac_mode property."""
    entity = FreeAtHomeClimateEntity(
        mock_climate_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    # State True -> HEAT_COOL
    mock_climate_channel.state = True
    assert entity.hvac_mode == HVACMode.HEAT_COOL

    # State False -> OFF
    mock_climate_channel.state = False
    assert entity.hvac_mode == HVACMode.OFF


async def test_state(mock_climate_channel):
    """Test state property."""
    entity = FreeAtHomeClimateEntity(
        mock_climate_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    # State True -> HEAT_COOL
    mock_climate_channel.state = True
    assert entity.state == HVACMode.HEAT_COOL

    # State False -> OFF
    mock_climate_channel.state = False
    assert entity.state == HVACMode.OFF


async def test_hvac_action(mock_climate_channel):
    """Test hvac_action property."""
    entity = FreeAtHomeClimateEntity(
        mock_climate_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    # Off mode -> Off action
    mock_climate_channel.state = False
    assert entity.hvac_action == HVACAction.OFF

    # On mode, heating > cooling -> Heating action
    mock_climate_channel.state = True
    mock_climate_channel.heating = 1
    mock_climate_channel.cooling = 0
    assert entity.hvac_action == HVACAction.HEATING

    # On mode, cooling > heating -> Cooling action
    mock_climate_channel.heating = 0
    mock_climate_channel.cooling = 1
    assert entity.hvac_action == HVACAction.COOLING

    # On mode, heating == cooling -> Idle action
    mock_climate_channel.heating = 0
    mock_climate_channel.cooling = 0
    assert entity.hvac_action == HVACAction.IDLE


async def test_target_temperature(mock_climate_channel):
    """Test target_temperature property."""
    entity = FreeAtHomeClimateEntity(
        mock_climate_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    # On mode -> returns value
    mock_climate_channel.state = True
    assert entity.target_temperature == 22.0

    # Off mode -> returns None
    mock_climate_channel.state = False
    assert entity.target_temperature is None


async def test_preset_mode(mock_climate_channel):
    """Test preset_mode property."""
    entity = FreeAtHomeClimateEntity(
        mock_climate_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    # eco_mode True -> "eco"
    mock_climate_channel.eco_mode = True
    assert entity.preset_mode == "eco"

    # eco_mode False -> None
    mock_climate_channel.eco_mode = False
    assert entity.preset_mode is None


async def test_async_set_hvac_mode(mock_climate_channel):
    """Test async_set_hvac_mode."""
    entity = FreeAtHomeClimateEntity(
        mock_climate_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    # Set to HEAT_COOL -> calls turn_on
    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    mock_climate_channel.turn_on.assert_called_once()

    # Set to OFF -> calls turn_off
    await entity.async_set_hvac_mode(HVACMode.OFF)
    mock_climate_channel.turn_off.assert_called_once()


async def test_async_turn_on(mock_climate_channel):
    """Test async_turn_on."""
    entity = FreeAtHomeClimateEntity(
        mock_climate_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )
    await entity.async_turn_on()
    mock_climate_channel.turn_on.assert_called_once()


async def test_async_turn_off(mock_climate_channel):
    """Test async_turn_off."""
    entity = FreeAtHomeClimateEntity(
        mock_climate_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )
    await entity.async_turn_off()
    mock_climate_channel.turn_off.assert_called_once()


async def test_async_set_preset_mode(mock_climate_channel):
    """Test async_set_preset_mode."""
    entity = FreeAtHomeClimateEntity(
        mock_climate_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    # Set to eco -> calls eco_on
    await entity.async_set_preset_mode("eco")
    mock_climate_channel.eco_on.assert_called_once()

    # Set to none -> calls eco_off
    await entity.async_set_preset_mode("none")
    mock_climate_channel.eco_off.assert_called_once()


async def test_async_set_temperature(mock_climate_channel):
    """Test async_set_temperature."""
    entity = FreeAtHomeClimateEntity(
        mock_climate_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    await entity.async_set_temperature(**{ATTR_TEMPERATURE: 24.5})
    mock_climate_channel.set_temperature.assert_called_once_with(24.5)


async def test_async_update(hass: HomeAssistant, mock_climate_channel):
    """Test async_update."""
    entity = FreeAtHomeClimateEntity(
        mock_climate_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )
    entity.hass = hass

    await entity.async_update()
    mock_climate_channel.refresh_state.assert_called_once()


async def test_callbacks(mock_climate_channel):
    """Test callbacks registration and removal."""
    entity = FreeAtHomeClimateEntity(
        mock_climate_channel,
        sysap_serial_number="SERIAL123",
        create_subdevices=False,
    )

    # Added to hass
    await entity.async_added_to_hass()
    assert mock_climate_channel.register_callback.call_count == 6

    # Removed from hass
    await entity.async_will_remove_from_hass()
    assert mock_climate_channel.remove_callback.call_count == 6
