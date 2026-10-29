"""Test virtual dimmer requests and feedback with the published library."""

import json
from pathlib import Path
import re
from unittest.mock import AsyncMock, Mock, call, patch

from abbfreeathome.bin.pairing import Pairing
from abbfreeathome.channels.virtual.virtual_dimming_actuator import (
    VirtualDimmingActuator,
)
from abbfreeathome.device import Device
import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.event import (
    EVENT_DESCRIPTIONS,
    FreeAtHomeEventEntity,
    async_setup_entry as async_setup_events,
)
from custom_components.abbfreeathome_ci.light import (
    FreeAtHomeLightEntity,
    async_setup_entry as async_setup_lights,
)
from homeassistant.components.light import ColorMode
from homeassistant.core import callback
from homeassistant.util.color import value_to_brightness

SERIAL = "6000F66D1DA7"
ONOFF_KEY = "EventVirtualDimmingActuatorOnOff"
DIMMING_KEY = "EventVirtualDimmingActuatorDimming"
BRIGHTNESS_KEY = "EventVirtualDimmingActuatorBrightness"


@pytest.fixture
def channel():
    """Create a real library channel with independent input/output datapoints."""
    device = Device(
        device_serial=SERIAL,
        device_id="virtual",
        display_name="Virtual Dimmer",
        api=Mock(set_datapoint=AsyncMock(), get_datapoint=AsyncMock()),
    )
    return VirtualDimmingActuator(
        device=device,
        channel_id="ch0000",
        channel_name="Virtual Dimmer",
        inputs={
            "idp0000": {"pairingID": Pairing.AL_SWITCH_ON_OFF.value, "value": "0"},
            "idp0001": {"pairingID": Pairing.AL_RELATIVE_SET_VALUE_CONTROL.value},
            "idp0002": {"pairingID": Pairing.AL_ABSOLUTE_SET_VALUE_CONTROL.value},
        },
        outputs={
            "odp0000": {"pairingID": Pairing.AL_INFO_ON_OFF.value, "value": "0"},
            "odp0001": {
                "pairingID": Pairing.AL_INFO_ACTUAL_DIMMING_VALUE.value,
                "value": "25",
            },
        },
        parameters={},
    )


@pytest.fixture
def light(channel):
    """Build the existing light entity around a virtual dimmer."""
    entity = FreeAtHomeLightEntity(channel, "SYSAP", False)
    entity.async_write_ha_state = Mock()
    return entity


@pytest.fixture
def events(channel):
    """Build existing event entities from the virtual dimmer descriptions."""
    return {
        key: FreeAtHomeEventEntity(
            channel,
            state_attribute=description["state_attribute"],
            entity_description_kwargs={"key": key}
            | description["entity_description_kwargs"],
            sysap_serial_number="SYSAP",
            create_subdevices=False,
            event_type_callback=description["event_type_callback"],
            extra_data=description.get("extra_data"),
        )
        for key, description in EVENT_DESCRIPTIONS.items()
        if description["channel_class"] is VirtualDimmingActuator
    }


async def test_setup(hass, mock_config_entry, channel):
    """Discover exactly one light and three independent request entities."""
    api = Mock()
    api.get_channels_by_class.side_effect = lambda channel_class: (
        [channel] if channel_class is VirtualDimmingActuator else []
    )
    hass.data[DOMAIN] = {mock_config_entry.entry_id: api}
    lights = []
    events = []
    await async_setup_lights(hass, mock_config_entry, lights.extend)
    await async_setup_events(hass, mock_config_entry, events.extend)

    assert len(lights) == 1
    assert type(lights[0]) is FreeAtHomeLightEntity
    assert lights[0].unique_id == f"{SERIAL}_ch0000_light"
    assert lights[0].supported_color_modes == {ColorMode.BRIGHTNESS}
    assert lights[0].color_temp_kelvin is None
    assert {entity.unique_id for entity in events} == {
        f"{SERIAL}_ch0000_{key}" for key in (ONOFF_KEY, DIMMING_KEY, BRIGHTNESS_KEY)
    }
    assert all(type(entity) is FreeAtHomeEventEntity for entity in events)
    assert all(
        entity.device_info["identifiers"] == {(DOMAIN, SERIAL)}
        for entity in [*lights, *events]
    )


@pytest.mark.parametrize(("brightness", "percentage"), [(1, 1), (128, 50), (255, 100)])
async def test_brightness_feedback(channel, light, brightness, percentage):
    """Brightness writes publish outputs and also report the light as on."""
    await light.async_turn_on(brightness=brightness)

    assert channel.device.api.set_datapoint.await_args_list == [
        call(
            device_serial=SERIAL,
            channel_id="ch0000",
            datapoint="odp0001",
            value=str(percentage),
        ),
        call(
            device_serial=SERIAL,
            channel_id="ch0000",
            datapoint="odp0000",
            value="1",
        ),
    ]
    assert light.is_on is True
    assert light.brightness == value_to_brightness((1, 100), percentage)
    light.async_write_ha_state.assert_called_once()
    assert channel.requested_state is False
    assert channel.requested_brightness is None


async def test_switch_feedback(channel, light):
    """Switch feedback preserves brightness and never writes request inputs."""
    await light.async_turn_on()
    await light.async_turn_off()
    assert channel.device.api.set_datapoint.await_args_list == [
        call(
            device_serial=SERIAL, channel_id="ch0000", datapoint="odp0000", value=value
        )
        for value in ("1", "0")
    ]
    assert light.is_on is False
    assert channel.brightness == 25
    assert channel.requested_state is False


async def test_feedback_failure_propagates(channel, light):
    """A failed feedback write is not reported as a successful state change."""
    channel.device.api.set_datapoint.side_effect = OSError("Disconnected")
    with pytest.raises(OSError, match="Disconnected"):
        await light.async_turn_on(brightness=255)
    assert light.is_on is False
    assert channel.brightness == 25
    assert channel.device.api.set_datapoint.await_count == 1
    light.async_write_ha_state.assert_not_called()


@pytest.mark.parametrize(
    ("key", "datapoint", "value", "event_type", "extra_data"),
    [
        (ONOFF_KEY, "idp0000", "1", "on", None),
        (ONOFF_KEY, "idp0000", "0", "off", None),
        (DIMMING_KEY, "idp0001", "9", "longpress_up", None),
        (DIMMING_KEY, "idp0001", "8", "longpress_up_release", None),
        (DIMMING_KEY, "idp0001", "1", "longpress_down", None),
        (DIMMING_KEY, "idp0001", "0", "longpress_down_release", None),
        (BRIGHTNESS_KEY, "idp0002", "0", "requested_brightness", 0.0),
        (BRIGHTNESS_KEY, "idp0002", "42.5", "requested_brightness", 42.5),
        (BRIGHTNESS_KEY, "idp0002", "100", "requested_brightness", 100.0),
    ],
)
async def test_request_events(
    channel, events, key, datapoint, value, event_type, extra_data
):
    """Each telegram, including repeats, emits only its input's event."""
    writes = {key: Mock() for key in events}
    for event_key, entity in events.items():
        entity.async_write_ha_state = writes[event_key]
        await entity.async_added_to_hass()

    entity = events[key]
    with patch.object(entity, "_trigger_event", wraps=entity._trigger_event) as trigger:
        channel.update_channel(datapoint, value)
        channel.update_channel(datapoint, value)

    assert trigger.call_args_list == [
        call(event_type, {"extra_data": extra_data}),
        call(event_type, {"extra_data": extra_data}),
    ]
    assert writes[key].call_count == 2
    assert all(not write.called for name, write in writes.items() if name != key)
    assert channel.state is False
    assert channel.brightness == 25
    channel.device.api.set_datapoint.assert_not_awaited()


async def test_invalid_requests(channel, events):
    """Ignore uninitialized and unknown requests rather than inventing events."""
    channel.update_channel("idp0000", None)
    for entity in events.values():
        entity.async_write_ha_state = Mock()
        await entity.async_added_to_hass()
        entity._async_handle_event()
        entity.async_write_ha_state.assert_not_called()

    channel.update_channel("idp0001", "invalid")
    for value in ("", "invalid", "-1", "101", "nan"):
        channel.update_channel("idp0002", value)

    for entity in events.values():
        entity.async_write_ha_state.assert_not_called()


@pytest.mark.parametrize("value", [None, "", "invalid", "2", "-1", "true"])
async def test_invalid_switching_telegrams(channel, events, value):
    """Malformed switching requests neither emit off nor replay a prior command."""
    entity = events[ONOFF_KEY]
    entity.async_write_ha_state = Mock()
    await entity.async_added_to_hass()

    with patch.object(entity, "_trigger_event", wraps=entity._trigger_event) as trigger:
        for valid_value, event_type in (("1", "on"), ("0", "off"), ("1", "on")):
            channel.update_channel("idp0000", valid_value)
            assert channel.requested_state is (valid_value == "1")
            trigger.assert_called_once_with(event_type, {"extra_data": None})
            entity.async_write_ha_state.assert_called_once()
            trigger.reset_mock()
            entity.async_write_ha_state.reset_mock()

            channel.update_channel("idp0000", value)
            assert channel.requested_state is None
            trigger.assert_not_called()
            entity.async_write_ha_state.assert_not_called()

    assert channel.state is False
    channel.device.api.set_datapoint.assert_not_awaited()


async def test_feedback_callbacks_and_cleanup(channel, light, events):
    """Feedback updates only the light; removal and re-add do not leak callbacks."""
    entities = [light, *events.values()]
    for entity in entities:
        entity.async_write_ha_state = Mock()
        await entity.async_added_to_hass()

    channel.update_channel("odp0000", "1")
    channel.update_channel("odp0001", "0")
    assert light.is_on is True
    assert light.brightness == 0
    assert light.async_write_ha_state.call_count == 2
    for entity in events.values():
        entity.async_write_ha_state.assert_not_called()

    for entity in entities:
        await entity.async_will_remove_from_hass()
        entity.async_write_ha_state.reset_mock()
    assert all(not callbacks for callbacks in channel._callbacks.values())
    channel.update_channel("idp0000", "1")
    channel.update_channel("odp0001", "50")
    assert all(not entity.async_write_ha_state.called for entity in entities)

    for entity in entities:
        await entity.async_added_to_hass()
    assert all(len(callbacks) == 1 for callbacks in channel._callbacks.values())
    channel.update_channel("idp0000", "1")
    events[ONOFF_KEY].async_write_ha_state.assert_called_once()


async def test_home_assistant_services_and_events(hass, mock_config_entry, channel):
    """Exercise HA service calls, real event state writes, and platform unloading."""
    api = Mock(ws_close=AsyncMock())
    api.get_channels_by_class.side_effect = lambda channel_class: (
        [channel] if channel_class is VirtualDimmingActuator else []
    )
    mock_config_entry.add_to_hass(hass)

    async def setup_entry(hass, entry):
        """Load the platforms without connecting to a physical SysAP."""
        hass.data[DOMAIN] = {entry.entry_id: api}
        await hass.config_entries.async_forward_entry_setups(entry, ["light", "event"])
        return True

    with patch(
        "custom_components.abbfreeathome_ci.async_setup_entry", side_effect=setup_entry
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    lights = hass.states.async_all("light")
    events = hass.states.async_all("event")
    assert len(lights) == 1
    assert len(events) == 3
    assert all(state.state == "unknown" for state in events)
    light_id = lights[0].entity_id

    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id, "brightness": 128}, blocking=True
    )
    assert hass.states.get(light_id).state == "on"
    assert hass.states.get(light_id).attributes["brightness"] == 128
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id, "brightness": 0}, blocking=True
    )
    assert hass.states.get(light_id).state == "off"
    assert channel.device.api.set_datapoint.await_args.kwargs == {
        "device_serial": SERIAL,
        "channel_id": "ch0000",
        "datapoint": "odp0000",
        "value": "0",
    }

    state_changes = []

    @callback
    def collect_state_change(event):
        """Collect state writes in event-loop order."""
        state_changes.append(event)

    unsubscribe = hass.bus.async_listen("state_changed", collect_state_change)
    channel.update_channel("idp0000", "1")
    channel.update_channel("idp0001", "9")
    channel.update_channel("idp0002", "42.5")
    channel.update_channel("idp0000", "1")
    await hass.async_block_till_done()
    unsubscribe()

    assert [
        event.data["new_state"].attributes["event_type"] for event in state_changes
    ] == ["on", "longpress_up", "requested_brightness", "on"]
    brightness_event = next(
        state
        for state in hass.states.async_all("event")
        if state.attributes["event_type"] == "requested_brightness"
    )
    assert brightness_event.attributes["extra_data"] == 42.5
    assert hass.states.get(light_id).state == "off"

    channel.update_channel("odp0000", "1")
    channel.update_channel("odp0001", "100")
    assert hass.states.get(light_id).state == "on"
    assert hass.states.get(light_id).attributes["brightness"] == 255

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert all(not callbacks for callbacks in channel._callbacks.values())


@pytest.mark.parametrize(
    "filename", ["strings.json", "translations/en.json", "translations/de.json"]
)
def test_event_translations(events, filename):
    """All new event types have schema-compliant, matching translations."""
    strings = json.loads(
        (Path("custom_components/abbfreeathome_ci") / filename).read_text(
            encoding="utf-8"
        )
    )
    for entity in events.values():
        translated = strings["entity"]["event"][
            entity.entity_description.translation_key
        ]
        event_types = translated["state_attributes"]["event_type"]["state"]
        assert set(event_types) == set(entity.event_types)
        assert all(
            re.fullmatch(r"[a-z0-9]+(?:[_-][a-z0-9]+)*", key) for key in event_types
        )
