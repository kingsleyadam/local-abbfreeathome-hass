"""Tests for parameter diagnostic sensors."""

import logging
from unittest.mock import Mock, patch

from abbfreeathome.channels.base import Base
from abbfreeathome.channels.temperature_sensor import TemperatureSensor
from abbfreeathome.device import Device
import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.sensor import (
    FreeAtHomeParametersSensor,
    FreeAtHomeSensorEntity,
    async_setup_entry,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_component import EntityComponent


@pytest.fixture
def parameter_device():
    """Create a device and real parameter callback sources."""
    device = Device(
        device_serial="ABB123456",
        device_id="test",
        display_name="Living room actuator",
        api=Mock(),
        parameters={"par0001": "0"},
    )
    for channel_id, channel_name, parameters in (
        ("ch0000", "Living room ceiling light", {"par0015": "130"}),
        (
            "ch0001",
            "Living room wall light",
            {"par0015": "60", "parffff": "unknown value"},
        ),
        ("ch0002", "Spare channel", {}),
    ):
        device.channels[channel_id] = Base(
            device=device,
            channel_id=channel_id,
            channel_name=channel_name,
            inputs={},
            outputs={},
            parameters=parameters,
        )
    return device


def test_parameter_sensor_properties(parameter_device):
    """Expose named parameters, unknown IDs and raw values on the parent."""
    entity = FreeAtHomeParametersSensor(
        parameter_device, list(parameter_device.channels.values())
    )

    assert entity.unique_id == "ABB123456_parameters"
    assert entity.device_info == {"identifiers": {(DOMAIN, "ABB123456")}}
    assert entity.entity_category is EntityCategory.DIAGNOSTIC
    assert entity.entity_registry_enabled_default is True
    assert entity.should_poll is False
    assert entity.has_entity_name is True
    assert entity.translation_key == "parameters"
    assert entity.native_value == 4
    assert entity.native_unit_of_measurement is None
    assert entity.state_class is None
    assert entity.extra_state_attributes == {
        "device_parameters": {"PID_LED_DAY_BRIGHTNESS": "0"},
        "channel_parameters": {
            "ch0000": {
                "name": "Living room ceiling light",
                "parameters": {"PID_AUTONOMOUS_SWITCH_OFF_TIME_DURATION": "130"},
            },
            "ch0001": {
                "name": "Living room wall light",
                "parameters": {
                    "PID_AUTONOMOUS_SWITCH_OFF_TIME_DURATION": "60",
                    "parffff": "unknown value",
                },
            },
        },
    }


@pytest.mark.parametrize("scope", ["device", "channel"])
def test_unknown_parameter_name_falls_back_to_id(parameter_device, scope):
    """Preserve unknown parameters at both device and channel scope."""
    source = (
        parameter_device if scope == "device" else parameter_device.channels["ch0000"]
    )
    source.update_parameter("parfffe", "raw value")
    entity = FreeAtHomeParametersSensor(
        parameter_device, list(parameter_device.channels.values())
    )
    attributes = entity.extra_state_attributes
    parameters = (
        attributes["device_parameters"]
        if scope == "device"
        else attributes["channel_parameters"]["ch0000"]["parameters"]
    )

    assert source.get_parameter_name("parfffe") is None
    assert parameters["parfffe"] == "raw value"
    assert entity.native_value == 5


def test_parameter_attributes_are_snapshots(parameter_device):
    """Updates must not mutate previously published state attributes."""
    entity = FreeAtHomeParametersSensor(
        parameter_device, list(parameter_device.channels.values())
    )
    attributes = entity.extra_state_attributes
    parameter_device.update_parameter("par0001", "1")
    parameter_device.channels["ch0000"].update_parameter("par0015", "140")

    assert attributes["device_parameters"]["PID_LED_DAY_BRIGHTNESS"] == "0"
    assert (
        attributes["channel_parameters"]["ch0000"]["parameters"][
            "PID_AUTONOMOUS_SWITCH_OFF_TIME_DURATION"
        ]
        == "130"
    )
    assert (
        entity.extra_state_attributes["device_parameters"]["PID_LED_DAY_BRIGHTNESS"]
        == "1"
    )
    assert (
        entity.extra_state_attributes["channel_parameters"]["ch0000"]["parameters"][
            "PID_AUTONOMOUS_SWITCH_OFF_TIME_DURATION"
        ]
        == "140"
    )


def test_channel_names_do_not_affect_keys(parameter_device):
    """Keep channels distinct and template keys stable across display-name changes."""
    entity = FreeAtHomeParametersSensor(
        parameter_device, list(parameter_device.channels.values())
    )
    original = entity.extra_state_attributes["channel_parameters"]
    for channel in parameter_device.channels.values():
        channel._channel_name = "Shared display name"
    renamed = entity.extra_state_attributes["channel_parameters"]

    assert renamed.keys() == original.keys()
    assert renamed["ch0000"] == {
        "name": "Shared display name",
        "parameters": {"PID_AUTONOMOUS_SWITCH_OFF_TIME_DURATION": "130"},
    }
    assert renamed["ch0001"] == {
        "name": "Shared display name",
        "parameters": {
            "PID_AUTONOMOUS_SWITCH_OFF_TIME_DURATION": "60",
            "parffff": "unknown value",
        },
    }
    assert original["ch0000"]["name"] == "Living room ceiling light"
    assert entity.native_value == 4


async def test_parameter_callbacks(parameter_device):
    """Subscribe to all included sources and remove every subscription."""
    entity = FreeAtHomeParametersSensor(
        parameter_device, list(parameter_device.channels.values())
    )
    with patch.object(entity, "async_write_ha_state") as write_state:
        await entity.async_added_to_hass()
        parameter_device.update_parameter("par0001", "1")
        parameter_device.channels["ch0000"].update_parameter("par0015", "140")
        parameter_device.channels["ch0001"].update_parameter("parffff", "new value")
        # Subscribe even to initially empty channels.
        parameter_device.channels["ch0002"].update_parameter("par1234", "0")
        assert write_state.call_count == 4
        assert entity.native_value == 5

        parameter_device.channels["ch0000"].update_parameter("par0015", "140")
        assert write_state.call_count == 4

        await entity.async_will_remove_from_hass()
        parameter_device.update_parameter("par0001", "2")
        for channel in parameter_device.channels.values():
            channel.update_parameter("par0015", "150")
        assert write_state.call_count == 4


async def test_parameter_state_updates_in_hass(hass, parameter_device):
    """Publish attribute-only changes and stop updating after removal."""
    entity = FreeAtHomeParametersSensor(
        parameter_device, list(parameter_device.channels.values())
    )
    entity.entity_id = "sensor.living_room_actuator_parameters"
    component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
    await component.async_add_entities([entity])

    old_state = hass.states.get(entity.entity_id)
    assert old_state.state == "4"
    assert old_state.attributes["channel_parameters"]["ch0000"] == {
        "name": "Living room ceiling light",
        "parameters": {"PID_AUTONOMOUS_SWITCH_OFF_TIME_DURATION": "130"},
    }

    parameter_device.channels["ch0000"].update_parameter("par0015", "140")
    state = hass.states.get(entity.entity_id)
    assert state.state == "4"
    assert state.attributes["channel_parameters"]["ch0000"] == {
        "name": "Living room ceiling light",
        "parameters": {"PID_AUTONOMOUS_SWITCH_OFF_TIME_DURATION": "140"},
    }
    assert old_state.attributes["channel_parameters"]["ch0000"] == {
        "name": "Living room ceiling light",
        "parameters": {"PID_AUTONOMOUS_SWITCH_OFF_TIME_DURATION": "130"},
    }

    parameter_device.update_parameter("par0001", "1")
    assert hass.states.get(entity.entity_id).attributes["device_parameters"] == {
        "PID_LED_DAY_BRIGHTNESS": "1"
    }

    parameter_device.channels["ch0002"].update_parameter("par1234", "0")
    assert hass.states.get(entity.entity_id).state == "5"

    await component.async_remove_entity(entity.entity_id)
    removed_state = hass.states.get(entity.entity_id)
    parameter_device.update_parameter("par0001", "2")
    assert hass.states.get(entity.entity_id) is removed_state


@pytest.mark.parametrize("create_subdevices", [False, True])
async def test_setup_parameter_sensors(
    hass, mock_config_entry, parameter_device, create_subdevices
):
    """Only expose included channels and keep the aggregate on the parent."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, "create_subdevices": create_subdevices},
    )
    api = Mock()
    api.get_channels_by_class.return_value = []
    api.get_devices.return_value = {parameter_device.device_serial: parameter_device}
    api.get_channels_by_device.return_value = [parameter_device.channels["ch0000"]]
    hass.data[DOMAIN] = {mock_config_entry.entry_id: api}
    entities = []

    await async_setup_entry(hass, mock_config_entry, entities.extend)

    assert len(entities) == 1
    entity = entities[0]
    assert entity.device_info == {"identifiers": {(DOMAIN, "ABB123456")}}
    assert entity.native_value == 2
    assert entity.extra_state_attributes["channel_parameters"] == {
        "ch0000": {
            "name": "Living room ceiling light",
            "parameters": {"PID_AUTONOMOUS_SWITCH_OFF_TIME_DURATION": "130"},
        }
    }
    with patch.object(entity, "async_write_ha_state") as write_state:
        await entity.async_added_to_hass()
        parameter_device.channels["ch0001"].update_parameter("par0015", "70")
        write_state.assert_not_called()
        await entity.async_will_remove_from_hass()


@pytest.mark.parametrize(
    ("include_channels", "device_parameters", "channel_parameters", "expected_count"),
    [
        (False, {"par0001": "0"}, {"par0015": "130"}, 0),
        (True, {}, {}, 0),
        (True, {"par0001": "0"}, {}, 1),
        (True, {}, {"par0015": "130"}, 1),
    ],
)
async def test_setup_parameter_sensor_eligibility(
    hass,
    mock_config_entry,
    include_channels,
    device_parameters,
    channel_parameters,
    expected_count,
):
    """Skip excluded and empty devices, but support either parameter scope."""
    device = Device(
        device_serial="ABB123456",
        device_id="test",
        display_name="Actuator",
        api=Mock(),
        parameters=device_parameters,
    )
    channel = Base(
        device=device,
        channel_id="ch0000",
        channel_name="Light",
        inputs={},
        outputs={},
        parameters=channel_parameters,
    )
    api = Mock()
    api.get_devices.return_value = {device.device_serial: device}
    api.get_channels_by_class.return_value = []
    api.get_channels_by_device.return_value = [channel] if include_channels else []
    hass.data[DOMAIN] = {mock_config_entry.entry_id: api}
    entities = []

    await async_setup_entry(hass, mock_config_entry, entities.extend)

    assert len(entities) == expected_count


async def test_setup_no_devices(hass, mock_config_entry):
    """Handle an installation without any devices."""
    api = Mock()
    api.get_devices.return_value = {}
    api.get_channels_by_class.return_value = []
    hass.data[DOMAIN] = {mock_config_entry.entry_id: api}
    entities = []

    await async_setup_entry(hass, mock_config_entry, entities.extend)

    assert entities == []


async def test_setup_preserves_measurement_sensors(
    hass, mock_config_entry, parameter_device
):
    """Parameter aggregates must not replace the existing measurement entities."""
    channel = Mock(spec=TemperatureSensor)
    channel.channel_name = "Living room temperature"
    channel.channel_id = "ch0003"
    channel.state = 21
    api = Mock()
    api.get_devices.return_value = {parameter_device.device_serial: parameter_device}
    api.get_channels_by_device.return_value = list(parameter_device.channels.values())
    api.get_channels_by_class.side_effect = lambda channel_class: (
        [channel] if channel_class is TemperatureSensor else []
    )
    hass.data[DOMAIN] = {mock_config_entry.entry_id: api}
    entities = []

    await async_setup_entry(hass, mock_config_entry, entities.extend)

    assert len(entities) == 2
    assert isinstance(entities[0], FreeAtHomeSensorEntity)
    assert entities[0].native_value == 21
    assert isinstance(entities[1], FreeAtHomeParametersSensor)
