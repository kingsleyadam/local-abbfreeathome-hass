"""Test ABB-free@home climate."""

from unittest.mock import AsyncMock, MagicMock, patch

from abbfreeathome.bin.function import Function
from abbfreeathome.bin.pairing import Pairing
from abbfreeathome.channels.room_temperature_controller import (
    RadiatorActuator,
    RoomTemperatureController,
)
from abbfreeathome.const import FUNCTION_CHANNEL_MAPPING

from custom_components.abbfreeathome_ci.climate import (
    FreeAtHomeClimateEntity,
    FreeAtHomeRadiatorClimateEntity,
    async_setup_entry,
)
from custom_components.abbfreeathome_ci.const import DOMAIN
from homeassistant.components.climate import ClimateEntityFeature
from homeassistant.components.climate.const import HVACAction, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant


def _radiator_outputs(
    *,
    on: str = "1",
    set_point: str = "21.5",
    measured: str = "20.42",
    state_indication: str = "96",
    heating_active: str = "0",
    heating_demand: str = "0",
) -> dict[str, dict[str, str | int]]:
    """Build the outputs of a FID_RADIATOR_ACTUATOR_MASTER channel."""
    return {
        "odp0000": {
            "pairingID": Pairing.AL_SET_POINT_TEMPERATURE.value,
            "value": set_point,
        },
        "odp0002": {
            "pairingID": Pairing.AL_CONTROLLER_ON_OFF.value,
            "value": on,
        },
        "odp0003": {
            "pairingID": Pairing.AL_STATE_INDICATION.value,
            "value": state_indication,
        },
        "odp0007": {
            "pairingID": Pairing.AL_MEASURED_TEMPERATURE.value,
            "value": measured,
        },
        "odp0008": {
            "pairingID": Pairing.AL_HEATING_ACTIVE.value,
            "value": heating_active,
        },
        "odp0009": {
            "pairingID": Pairing.AL_HEATING_DEMAND.value,
            "value": heating_demand,
        },
    }


def _radiator_inputs() -> dict[str, dict[str, str | int]]:
    """Build the inputs of a FID_RADIATOR_ACTUATOR_MASTER channel."""
    return {
        "idp0004": {"pairingID": Pairing.AL_ECO_ON_OFF.value, "value": "0"},
        "idp0005": {
            "pairingID": Pairing.AL_CONTROLLER_ON_OFF_REQUEST.value,
            "value": "0",
        },
        "idp0009": {
            "pairingID": Pairing.AL_INFO_ABSOLUTE_SET_POINT_REQUEST.value,
            "value": "22",
        },
    }


def _radiator_channel(**kwargs) -> RadiatorActuator:
    """Build a RadiatorActuator channel backed by a mocked api."""
    device = MagicMock()
    device.api.set_datapoint = AsyncMock()
    device.api.get_datapoint = AsyncMock(return_value=["1"])

    return RadiatorActuator(
        device=device,
        channel_id="ch0000",
        channel_name="Hobbyraum",
        inputs=_radiator_inputs(),
        outputs=_radiator_outputs(**kwargs),
        parameters={},
    )


def _mock_radiator_entity_channel() -> MagicMock:
    """Build a mocked radiator channel for entity level tests."""
    channel = MagicMock(spec=RadiatorActuator)
    channel.channel_name = "Hobbyraum"
    channel.channel_id = "ch0000"
    channel.device_serial = "ABB7F630796A"
    channel.device_name = "Hobbyraum"
    channel.room_name = "Hobbyraum"
    channel.device.is_multi_device = False
    channel.state = True
    channel.current_temperature = 20.42
    channel.target_temperature = 21.5
    channel.eco_mode = False
    channel.heating = 0
    channel.heating_active = False
    channel.turn_on = AsyncMock()
    channel.turn_off = AsyncMock()

    return channel


async def _setup_entry_for_class(
    hass: HomeAssistant, mock_config_entry, expected_class, channel
) -> list:
    """Run async_setup_entry returning only channels of the given class."""
    mock_config_entry.add_to_hass(hass)

    mock_free_at_home = MagicMock()
    mock_free_at_home.get_channels_by_class.side_effect = lambda channel_class: (
        [channel] if channel_class is expected_class else []
    )
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    entities_added = []
    async_add_entities = MagicMock(
        side_effect=lambda generator: entities_added.extend(list(generator))
    )
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    return entities_added


async def test_async_setup_entry_no_climate_channels(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup with no climate entities."""
    mock_config_entry.add_to_hass(hass)

    mock_free_at_home = MagicMock()
    mock_free_at_home.get_channels_by_class.return_value = []
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    async_add_entities = MagicMock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # Once for room temperature controllers, once for radiator thermostats
    assert async_add_entities.call_count == 2


async def test_async_setup_entry_with_room_temperature_controller(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup with a room temperature controller."""
    channel = MagicMock(spec=RoomTemperatureController)
    channel.channel_name = "Wohnzimmer"
    channel.channel_id = "ch0000"
    channel.device_serial = "ABB7F57FFFE12345"
    channel.device.is_multi_device = False

    entities_added = await _setup_entry_for_class(
        hass, mock_config_entry, RoomTemperatureController, channel
    )

    assert len(entities_added) == 1
    entity = entities_added[0]

    assert isinstance(entity, FreeAtHomeClimateEntity)
    assert not isinstance(entity, FreeAtHomeRadiatorClimateEntity)
    assert entity.entity_description.key == "RoomTemperatureController"
    assert entity.unique_id == "ABB7F57FFFE12345_ch0000_climate"
    assert entity.hvac_modes == [HVACMode.HEAT_COOL, HVACMode.OFF]


async def test_async_setup_entry_with_radiator_actuator(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup with a radiator thermostat."""
    entities_added = await _setup_entry_for_class(
        hass, mock_config_entry, RadiatorActuator, _mock_radiator_entity_channel()
    )

    assert len(entities_added) == 1
    entity = entities_added[0]

    assert isinstance(entity, FreeAtHomeRadiatorClimateEntity)
    assert entity.entity_description.key == "RadiatorActuator"
    assert entity.entity_description.name == "Hobbyraum"
    assert entity.unique_id == "ABB7F630796A_ch0000_climate"
    assert entity.hvac_modes == [HVACMode.HEAT, HVACMode.OFF]
    assert entity.preset_modes == ["none", "eco"]


def test_radiator_entity_reports_heat_instead_of_heat_cool() -> None:
    """Test the radiator entity never offers a cooling mode."""
    channel = _mock_radiator_entity_channel()
    entity = FreeAtHomeRadiatorClimateEntity(
        channel, sysap_serial_number="TEST123456", create_subdevices=False
    )

    assert entity.hvac_mode == HVACMode.HEAT
    assert entity.state == HVACMode.HEAT
    assert entity.hvac_action == HVACAction.IDLE

    channel.heating_active = True
    assert entity.hvac_action == HVACAction.HEATING

    channel.state = False
    assert entity.hvac_mode == HVACMode.OFF
    assert entity.state == HVACMode.OFF
    assert entity.hvac_action == HVACAction.OFF
    assert entity.target_temperature is None


def test_radiator_entity_extra_state_attributes() -> None:
    """Test the radiator entity reports heating instead of cooling."""
    channel = _mock_radiator_entity_channel()
    channel.heating = 42
    channel.heating_active = True
    entity = FreeAtHomeRadiatorClimateEntity(
        channel, sysap_serial_number="TEST123456", create_subdevices=False
    )

    assert entity.extra_state_attributes == {
        "heating": 42,
        "heating_active": True,
    }


async def test_radiator_entity_set_hvac_mode() -> None:
    """Test setting the hvac mode on a radiator entity."""
    channel = _mock_radiator_entity_channel()
    entity = FreeAtHomeRadiatorClimateEntity(
        channel, sysap_serial_number="TEST123456", create_subdevices=False
    )

    await entity.async_set_hvac_mode(HVACMode.HEAT)
    channel.turn_on.assert_awaited_once()

    await entity.async_set_hvac_mode(HVACMode.OFF)
    channel.turn_off.assert_awaited_once()

    # HEAT_COOL is not offered and must not switch the thermostat on
    channel.turn_on.reset_mock()
    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    channel.turn_on.assert_not_awaited()


async def test_radiator_entity_registers_heating_active_callback() -> None:
    """Test the radiator entity subscribes to every channel attribute."""
    channel = _radiator_channel()
    entity = FreeAtHomeRadiatorClimateEntity(
        channel, sysap_serial_number="TEST123456", create_subdevices=False
    )

    await entity.async_added_to_hass()
    assert "heating_active" in channel._callbacks

    await entity.async_will_remove_from_hass()
    assert not channel._callbacks["heating_active"]


def test_radiator_channel_reads_state_from_outputs() -> None:
    """Test the channel picks up its state from the free@home outputs."""
    channel = _radiator_channel(
        on="1", set_point="21.5", measured="20.42", state_indication="68"
    )

    assert channel.state is True
    assert channel.target_temperature == 21.5
    assert channel.current_temperature == 20.42
    assert channel.eco_mode is True
    assert channel.heating_active is False


def test_radiator_channel_heating_state() -> None:
    """Test the heating state comes from the radiator specific pairings."""
    channel = _radiator_channel()

    assert channel._refresh_state_from_datapoint(
        {"pairingID": Pairing.AL_HEATING_ACTIVE.value, "value": "1"}
    ) == ["heating_active"]
    assert channel.heating_active is True


def test_radiator_channel_demand_change_notifies_heating_active() -> None:
    """Test a demand change that flips heating_active reports both attributes.

    The climate entity derives its hvac_action from heating_active and only
    redraws on that callback. A demand reported without the active flag must
    therefore fire it too, or the heating indicator goes stale.
    """
    channel = _radiator_channel(heating_active="0", heating_demand="0")
    assert channel.heating_active is False

    assert channel._refresh_state_from_datapoint(
        {"pairingID": Pairing.AL_HEATING_DEMAND.value, "value": "55"}
    ) == ["heating", "heating_active"]
    assert channel.heating == 55
    assert channel.heating_active is True

    # Still heating, so only the demand itself changed
    assert channel._refresh_state_from_datapoint(
        {"pairingID": Pairing.AL_HEATING_DEMAND.value, "value": "70"}
    ) == ["heating"]


def test_radiator_channel_heating_active_falls_back_to_demand() -> None:
    """Test a demand without an active flag still counts as heating."""
    channel = _radiator_channel(heating_active="0", heating_demand="30")

    assert channel.heating == 30
    assert channel.heating_active is True


def test_radiator_channel_ignores_unparsable_demand() -> None:
    """Test a non numeric heating demand does not raise."""
    channel = _radiator_channel()

    channel._refresh_state_from_datapoint(
        {"pairingID": Pairing.AL_HEATING_DEMAND.value, "value": ""}
    )

    assert channel.heating == 0


async def test_radiator_channel_control_datapoints() -> None:
    """Test the channel writes to the expected free@home datapoints."""
    channel = _radiator_channel()

    await channel.set_temperature(21.5)
    await channel.turn_on()
    await channel.eco_on()

    written = [
        call.kwargs["datapoint"]
        for call in channel.device.api.set_datapoint.await_args_list
    ]
    assert written == ["idp0009", "idp0005", "idp0004"]


def test_library_maps_the_radiator_function() -> None:
    """Test the library itself maps the radiator thermostat function.

    The integration relies on local-abbfreeathome 3.9.0 for this. Before that
    release these channels were skipped on load and never reached Home
    Assistant at all.
    """
    assert (
        FUNCTION_CHANNEL_MAPPING[Function.FID_RADIATOR_ACTUATOR_MASTER]
        is RadiatorActuator
    )


def _mock_rtc_channel() -> MagicMock:
    """Build a mocked room temperature controller channel."""
    channel = MagicMock(spec=RoomTemperatureController)
    channel.channel_name = "Wohnzimmer"
    channel.channel_id = "ch0000"
    channel.device_serial = "ABB7F57FFFE12345"
    channel.device_name = "Wohnzimmer RTC"
    channel.room_name = "Wohnzimmer"
    channel.device.is_multi_device = False
    channel.device.device_id = "1234"
    channel.state = True
    channel.current_temperature = 21.3
    channel.target_temperature = 21.0
    channel.eco_mode = False
    channel.heating = 0
    channel.cooling = 0
    channel.turn_on = AsyncMock()
    channel.turn_off = AsyncMock()
    channel.eco_on = AsyncMock()
    channel.eco_off = AsyncMock()
    channel.set_temperature = AsyncMock()
    channel.refresh_state = AsyncMock()

    return channel


def _rtc_entity(channel, *, create_subdevices: bool = False) -> FreeAtHomeClimateEntity:
    """Build a room temperature controller entity."""
    return FreeAtHomeClimateEntity(
        channel,
        sysap_serial_number="TEST123456",
        create_subdevices=create_subdevices,
    )


def test_rtc_entity_static_properties() -> None:
    """Test the fixed properties of the room temperature controller entity."""
    entity = _rtc_entity(_mock_rtc_channel())

    assert entity.temperature_unit == UnitOfTemperature.CELSIUS
    assert entity.target_temperature_step == 0.5
    assert entity.min_temp == 7.0
    assert entity.max_temp == 35.0
    assert entity.current_temperature == 21.3
    assert entity.supported_features == (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )
    assert entity.extra_state_attributes == {"heating": 0, "cooling": 0}


def test_rtc_entity_device_info() -> None:
    """Test a single channel device is linked to the device itself."""
    entity = _rtc_entity(_mock_rtc_channel())

    assert entity.device_info == {"identifiers": {(DOMAIN, "ABB7F57FFFE12345")}}


def test_rtc_entity_device_info_with_subdevices() -> None:
    """Test a multi channel device gets a sub device per channel."""
    channel = _mock_rtc_channel()
    channel.device.is_multi_device = True
    entity = _rtc_entity(channel, create_subdevices=True)
    entity.platform = MagicMock()

    with patch(
        "custom_components.abbfreeathome_ci.climate.async_get_via_device_kwargs",
        return_value={"via_device_id": "parent_device_id"},
    ) as mock_via_device_kwargs:
        device_info = entity.device_info

    assert device_info["identifiers"] == {(DOMAIN, "ABB7F57FFFE12345_ch0000")}
    assert device_info["name"] == "Wohnzimmer RTC (ch0000)"
    assert device_info["serial_number"] == "ABB7F57FFFE12345_ch0000"
    assert device_info["hw_version"] == "1234 (sub)"
    assert device_info["suggested_area"] == "Wohnzimmer"
    assert device_info["via_device_id"] == "parent_device_id"
    mock_via_device_kwargs.assert_called_once_with(
        entity.hass, entity.platform.config_entry.entry_id, "ABB7F57FFFE12345"
    )


def test_rtc_entity_hvac_mode_and_state() -> None:
    """Test the controller reports HEAT_COOL when on and OFF when off."""
    channel = _mock_rtc_channel()
    entity = _rtc_entity(channel)

    assert entity.hvac_mode == HVACMode.HEAT_COOL
    assert entity.state == HVACMode.HEAT_COOL
    assert entity.target_temperature == 21.0

    channel.state = False
    assert entity.hvac_mode == HVACMode.OFF
    assert entity.state == HVACMode.OFF
    assert entity.target_temperature is None


def test_rtc_entity_hvac_action() -> None:
    """Test the action follows the heating and cooling actuating values."""
    channel = _mock_rtc_channel()
    entity = _rtc_entity(channel)

    assert entity.hvac_action == HVACAction.IDLE

    channel.heating = 40
    assert entity.hvac_action == HVACAction.HEATING

    channel.heating = 0
    channel.cooling = 40
    assert entity.hvac_action == HVACAction.COOLING

    channel.state = False
    assert entity.hvac_action == HVACAction.OFF


def test_rtc_entity_preset_mode() -> None:
    """Test the preset follows the channel's eco mode."""
    channel = _mock_rtc_channel()
    entity = _rtc_entity(channel)

    assert entity.preset_modes == ["none", "eco"]
    assert entity.preset_mode is None

    channel.eco_mode = True
    assert entity.preset_mode == "eco"


async def test_rtc_entity_set_hvac_mode() -> None:
    """Test setting the hvac mode switches the controller."""
    channel = _mock_rtc_channel()
    entity = _rtc_entity(channel)

    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    channel.turn_on.assert_awaited_once()

    await entity.async_set_hvac_mode(HVACMode.OFF)
    channel.turn_off.assert_awaited_once()

    # HEAT is not offered by the controller and must not switch it on
    channel.turn_on.reset_mock()
    await entity.async_set_hvac_mode(HVACMode.HEAT)
    channel.turn_on.assert_not_awaited()


async def test_rtc_entity_turn_on_and_off() -> None:
    """Test turning the controller on and off."""
    channel = _mock_rtc_channel()
    entity = _rtc_entity(channel)

    await entity.async_turn_on()
    channel.turn_on.assert_awaited_once()

    await entity.async_turn_off()
    channel.turn_off.assert_awaited_once()


async def test_rtc_entity_set_preset_mode() -> None:
    """Test the eco preset toggles the channel's eco mode."""
    channel = _mock_rtc_channel()
    entity = _rtc_entity(channel)

    await entity.async_set_preset_mode("eco")
    channel.eco_on.assert_awaited_once()

    await entity.async_set_preset_mode("none")
    channel.eco_off.assert_awaited_once()


async def test_rtc_entity_set_temperature() -> None:
    """Test setting the target temperature."""
    channel = _mock_rtc_channel()
    entity = _rtc_entity(channel)

    await entity.async_set_temperature(**{ATTR_TEMPERATURE: 22.5})

    channel.set_temperature.assert_awaited_once_with(22.5)


async def test_rtc_entity_update() -> None:
    """Test a manual update refreshes the channel state."""
    channel = _mock_rtc_channel()
    entity = _rtc_entity(channel)

    await entity.async_update()

    channel.refresh_state.assert_awaited_once()
