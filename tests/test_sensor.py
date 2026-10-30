"""Tests for parameter diagnostic sensors."""

import logging
from runpy import run_path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from abbfreeathome.channels.base import Base
from abbfreeathome.channels.heating_cooling_sensor import HeatingCoolingSensor
from abbfreeathome.channels.temperature_sensor import TemperatureSensor
from abbfreeathome.device import Device
import pytest

from custom_components.abbfreeathome_ci import sensor as sensor_platform
from custom_components.abbfreeathome_ci.const import DOMAIN, MANUFACTURER
from custom_components.abbfreeathome_ci.sensor import (
    FreeAtHomeParametersSensor,
    FreeAtHomeSensorEntity,
    async_setup_entry,
)
from homeassistant import const
from homeassistant.components.sensor import SensorDeviceClass
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


@pytest.mark.parametrize(
    ("create_subdevices", "multi_device"), [(False, True), (True, False)]
)
async def test_setup_parameter_sensors(
    hass, mock_config_entry, parameter_device, create_subdevices, multi_device
):
    """Aggregate unless both sub-device creation and multi-device detection apply."""
    if not multi_device:
        parameter_device._floor = "01"
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


@pytest.mark.parametrize("has_device_parameters", [False, True])
async def test_setup_split_parameter_sensors(
    hass, mock_config_entry, parameter_device, has_device_parameters
):
    """Give the parent device parameters and each included child its own parameters."""
    if not has_device_parameters:
        parameter_device.parameters.clear()
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, "create_subdevices": True},
    )
    api = Mock()
    api.get_devices.return_value = {parameter_device.device_serial: parameter_device}
    api.get_channels_by_class.return_value = []
    # The second populated channel is excluded by the integration's filters.
    api.get_channels_by_device.return_value = [
        parameter_device.channels["ch0000"],
        parameter_device.channels["ch0002"],
    ]
    hass.data[DOMAIN] = {mock_config_entry.entry_id: api}
    entities = []

    await async_setup_entry(hass, mock_config_entry, entities.extend)

    assert len(entities) == 1 + has_device_parameters
    child = entities[-1]
    assert child.unique_id == "ABB123456_ch0000_parameters"
    assert child.native_value == 1
    assert child.extra_state_attributes == {
        "channel_parameters": {
            "ch0000": {
                "name": "Living room ceiling light",
                "parameters": {"PID_AUTONOMOUS_SWITCH_OFF_TIME_DURATION": "130"},
            }
        }
    }
    child.hass = hass
    child.platform = Mock(config_entry=mock_config_entry)
    with patch(
        "custom_components.abbfreeathome_ci.sensor.async_get_via_device_kwargs",
        return_value={"via_device": (DOMAIN, "ABB123456")},
    ) as parent_link:
        info = child.device_info
    assert info["identifiers"] == {(DOMAIN, "ABB123456_ch0000")}
    assert info["name"] == "Living room actuator (ch0000)"
    assert info["via_device"] == (DOMAIN, "ABB123456")
    parent_link.assert_called_once_with(hass, mock_config_entry.entry_id, "ABB123456")

    with patch.object(child, "async_write_ha_state") as child_write:
        await child.async_added_to_hass()
        parameter_device.update_parameter("par0001", "1")
        parameter_device.channels["ch0001"].update_parameter("par0015", "70")
        child_write.assert_not_called()
        parameter_device.channels["ch0000"].update_parameter("par0015", "140")
        child_write.assert_called_once()
        await child.async_will_remove_from_hass()
        parameter_device.channels["ch0000"].update_parameter("par0015", "150")
        child_write.assert_called_once()

    if has_device_parameters:
        parent = entities[0]
        assert parent.unique_id == "ABB123456_parameters"
        assert parent.device_info == {"identifiers": {(DOMAIN, "ABB123456")}}
        assert parent.native_value == 1
        assert parent.extra_state_attributes == {
            "device_parameters": {"PID_LED_DAY_BRIGHTNESS": "1"}
        }
        with patch.object(parent, "async_write_ha_state") as parent_write:
            await parent.async_added_to_hass()
            parameter_device.channels["ch0000"].update_parameter("par0015", "160")
            parent_write.assert_not_called()
            parameter_device.update_parameter("par0001", "2")
            parent_write.assert_called_once()
            await parent.async_will_remove_from_hass()
            parameter_device.update_parameter("par0001", "3")
            parent_write.assert_called_once()


@pytest.mark.parametrize("scope", ["device", "channel", "neither"])
def test_empty_parameter_groups_are_omitted(parameter_device, scope):
    """Only publish nonempty parameter groups."""
    if scope != "device":
        parameter_device.parameters.clear()
    if scope != "channel":
        for channel in parameter_device.channels.values():
            channel.parameters.clear()
    entity = FreeAtHomeParametersSensor(
        parameter_device, list(parameter_device.channels.values())
    )

    assert ("device_parameters" in entity.extra_state_attributes) == (scope == "device")
    assert ("channel_parameters" in entity.extra_state_attributes) == (
        scope == "channel"
    )


@pytest.mark.parametrize("create_subdevices", [False, True])
async def test_combined_actuator_parameter_counts(
    hass, mock_config_entry, create_subdevices
):
    """Match the reported device's six contact and eight actuator channels."""
    device = Device(
        device_serial="TEST_COMBINED",
        device_id="B008",
        display_name="Combined actuator",
        api=Mock(),
        parameters={"par0026": "1"},
    )
    for index in range(16):
        parameters = (
            {"par0010": "2"} if index < 6 else {"par0028": "60", "par0027": "1"}
        )
        channel_id = f"ch{index:04x}"
        device.channels[channel_id] = Base(
            device=device,
            channel_id=channel_id,
            channel_name=f"Channel {index}",
            inputs={},
            outputs={},
            parameters=parameters,
        )
    # Two unused channels are filtered out upstream, not by their display name.
    included_channels = [
        channel
        for index, channel in enumerate(device.channels.values())
        if index not in (6, 7)
    ]
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, "create_subdevices": create_subdevices},
    )
    api = Mock()
    api.get_devices.return_value = {device.device_serial: device}
    api.get_channels_by_class.return_value = []
    api.get_channels_by_device.return_value = included_channels
    hass.data[DOMAIN] = {mock_config_entry.entry_id: api}
    entities = []

    await async_setup_entry(hass, mock_config_entry, entities.extend)

    assert sum(entity.native_value for entity in entities) == 23
    if create_subdevices:
        assert len(entities) == 15
        assert [entity.native_value for entity in entities] == [
            1,
            *([1] * 6),
            *([2] * 8),
        ]
        assert entities[0].extra_state_attributes == {
            "device_parameters": {"PID_CHANNEL_SELECTOR_8_GANG": "1"}
        }
        for entity, channel in zip(entities[1:], included_channels, strict=True):
            assert entity.unique_id == f"TEST_COMBINED_{channel.channel_id}_parameters"
            assert set(entity.extra_state_attributes) == {"channel_parameters"}
            assert list(entity.extra_state_attributes["channel_parameters"]) == [
                channel.channel_id
            ]
    else:
        assert len(entities) == 1
        assert len(entities[0].extra_state_attributes["channel_parameters"]) == 14


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


async def test_setup_heating_cooling_sensor(hass, mock_config_entry):
    """Expose the heating/cooling changeover as an enum sensor."""
    channel = HeatingCoolingSensor(
        device=Mock(spec=Device),
        channel_id="ch0000",
        channel_name="Umschalten Heizen / Kühlen",
        inputs={},
        outputs={"odp0007": {"pairingID": 309, "value": "0"}},
        parameters={},
    )
    api = Mock()
    api.get_devices.return_value = {}
    api.get_channels_by_class.side_effect = lambda channel_class: (
        [channel] if channel_class is HeatingCoolingSensor else []
    )
    hass.data[DOMAIN] = {mock_config_entry.entry_id: api}
    entities = []

    await async_setup_entry(hass, mock_config_entry, entities.extend)

    assert len(entities) == 1
    entity = entities[0]
    assert entity.device_class == SensorDeviceClass.ENUM
    assert entity.options == ["unknown", "heating", "cooling"]
    assert entity.translation_key == "heating_cooling_sensor"
    assert entity.native_value == "heating"

    channel.update_channel("AL_HEATING_COOLING/odp0007", "1")
    assert entity.native_value == "cooling"


@pytest.mark.parametrize("modern_units", [False, True])
def test_parts_per_million_compatibility(monkeypatch, modern_units):
    """Use the modern unit when available, otherwise use the legacy constant."""
    monkeypatch.setattr(
        const, "CONCENTRATION_PARTS_PER_MILLION", "legacy_ppm", raising=False
    )
    if modern_units:
        monkeypatch.setattr(
            const,
            "UnitOfRatio",
            SimpleNamespace(PARTS_PER_MILLION="modern_ppm"),
            raising=False,
        )
    else:
        monkeypatch.delattr(const, "UnitOfRatio", raising=False)

    sensor = run_path(
        sensor_platform.__file__, run_name="custom_components.abbfreeathome_ci.sensor"
    )
    expected_unit = "modern_ppm" if modern_units else "legacy_ppm"

    assert sensor["PARTS_PER_MILLION"] == expected_unit
    assert (
        sensor["SENSOR_DESCRIPTIONS"]["AirQualitySensorCO2"][
            "entity_description_kwargs"
        ]["native_unit_of_measurement"]
        == expected_unit
    )


@pytest.mark.parametrize(
    ("create_subdevices", "multi_device"), [(False, True), (True, False), (True, True)]
)
async def test_measurement_sensor_properties_and_callbacks(
    hass, mock_config_entry, parameter_device, create_subdevices, multi_device
):
    """Preserve measurement state, device placement and callback lifecycle."""
    if not multi_device:
        parameter_device._floor = "01"
    channel = Mock(
        spec=TemperatureSensor,
        device=parameter_device,
        device_serial=parameter_device.device_serial,
        device_name=parameter_device.display_name,
        channel_id="ch0003",
        channel_name="Living room temperature",
        room_name="Living room",
        state=21,
    )
    entity = FreeAtHomeSensorEntity(
        channel,
        value_attribute="state",
        entity_description_kwargs={"key": "TemperatureSensor"},
        sysap_serial_number="SYSAP123",
        create_subdevices=create_subdevices,
    )
    assert entity.unique_id == "ABB123456_ch0003_TemperatureSensor"
    assert entity.native_value == 21
    channel.state = None
    assert entity.native_value is None
    assert entity.should_poll is False
    assert entity.name == "Living room temperature"

    entity.hass = hass
    entity.platform = Mock(config_entry=mock_config_entry)
    with patch(
        "custom_components.abbfreeathome_ci.sensor.async_get_via_device_kwargs",
        return_value={"via_device": (DOMAIN, "ABB123456")},
    ) as parent_link:
        info = entity.device_info
    if create_subdevices and multi_device:
        assert info == {
            "identifiers": {(DOMAIN, "ABB123456_ch0003")},
            "name": "Living room actuator (ch0003)",
            "manufacturer": MANUFACTURER,
            "serial_number": "ABB123456_ch0003",
            "hw_version": "test (sub)",
            "suggested_area": "Living room",
            "via_device": (DOMAIN, "ABB123456"),
        }
        parent_link.assert_called_once_with(
            hass, mock_config_entry.entry_id, "ABB123456"
        )
    else:
        assert info == {"identifiers": {(DOMAIN, "ABB123456")}}
        parent_link.assert_not_called()

    await entity.async_added_to_hass()
    channel.register_callback.assert_called_once_with(
        callback_attribute="state", callback=entity.async_write_ha_state
    )
    await entity.async_will_remove_from_hass()
    channel.remove_callback.assert_called_once_with(
        callback_attribute="state", callback=entity.async_write_ha_state
    )
