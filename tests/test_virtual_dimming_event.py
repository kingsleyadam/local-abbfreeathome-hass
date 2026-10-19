"""Test virtual dimmer events using real library channels and WebSocket dispatch."""

from unittest.mock import AsyncMock, Mock, call, patch

from abbfreeathome import FreeAtHome, FreeAtHomeApi
from abbfreeathome.bin.interface import Interface
from abbfreeathome.channels.switch_sensor import DimmingSensor, DimmingSensorState
from abbfreeathome.channels.virtual.virtual_dimming_actuator import (
    VirtualDimmingActuator,
)
from abbfreeathome.channels.virtual.virtual_switch_actuator import VirtualSwitchActuator
from abbfreeathome.device import Device
from abbfreeathome.floorplan import Floorplan
import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.event import (
    EVENT_DESCRIPTIONS,
    FreeAtHomeEventEntity,
    FreeAtHomeVirtualDimmingEventEntity,
    async_setup_entry,
)
from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.core import callback

DIMMER_KEY = "EventVirtualDimmingActuator"
SWITCH_KEY = "EventVirtualSwitchActuatorOnOff"
SERIAL = "6000F66D1DA7"
EVENT_TYPES = [
    "On",
    "Off",
    "longpress_up",
    "longpress_up_release",
    "longpress_down",
    "longpress_down_release",
]


@pytest.fixture
def freeathome():
    """Load real virtual dimmer and switch channels through library mappings."""
    api = AsyncMock(spec=FreeAtHomeApi)
    # Test live requests after the reconnect snapshot has finished.
    api.is_priming = False
    device = Device(
        device_serial=SERIAL,
        device_id="test",
        display_name="Virtual actuators",
        api=api,
        interface=Interface.VIRTUAL_DEVICE,
        channels_data={
            "ch0000": {
                "functionID": "0012",
                "displayName": "Dimmer",
                "inputs": {
                    "idp0000": {"pairingID": 1, "value": "0"},
                    "idp0001": {"pairingID": 16, "value": "0"},
                },
                "outputs": {"odp0000": {"pairingID": 256, "value": "0"}},
            },
            "ch0001": {
                "functionID": "0007",
                "displayName": "Switch",
                "inputs": {"idp0000": {"pairingID": 1, "value": "0"}},
                "outputs": {"odp0000": {"pairingID": 256, "value": "0"}},
            },
        },
    )
    device.load_channels(Floorplan({}))
    instance = FreeAtHome(api, include_orphan_channels=True)
    instance._devices[SERIAL] = device
    return instance


@pytest.fixture
async def entities(hass, mock_config_entry, freeathome):
    """Create entities through platform setup and register their callbacks."""
    hass.data[DOMAIN] = {mock_config_entry.entry_id: freeathome}
    added = []
    await async_setup_entry(hass, mock_config_entry, added.extend)
    for entity in added:
        entity.hass = hass
        await entity.async_added_to_hass()
    yield {entity.entity_description.key: entity for entity in added}
    for entity in added:
        await entity.async_will_remove_from_hass()


def test_description():
    """Expose exactly the supported commands with the existing enum semantics."""
    description = EVENT_DESCRIPTIONS[DIMMER_KEY]
    assert description["channel_class"] is VirtualDimmingActuator
    assert description["entity_description_kwargs"]["event_types"] == EVENT_TYPES
    assert (
        description["entity_description_kwargs"]["device_class"]
        is EventDeviceClass.BUTTON
    )
    assert EVENT_TYPES[2:] == [
        state.name
        for state in DimmingSensorState
        if state is not DimmingSensorState.unknown
    ]


async def test_setup_recognizes_dimmer_once(entities):
    """A dimmer produces one event entity, not an additional switch entity."""
    assert set(entities) == {DIMMER_KEY, SWITCH_KEY}
    dimmer = entities[DIMMER_KEY]
    assert isinstance(dimmer, EventEntity)
    assert type(dimmer) is FreeAtHomeVirtualDimmingEventEntity
    assert type(dimmer._channel) is VirtualDimmingActuator
    assert dimmer.unique_id == f"{SERIAL}_ch0000_{DIMMER_KEY}"
    assert type(entities[SWITCH_KEY]) is FreeAtHomeEventEntity


@pytest.mark.parametrize(
    ("datapoint", "value", "expected"),
    [
        ("idp0000", "1", "On"),
        ("idp0000", "0", "Off"),
        ("idp0001", "9", "longpress_up"),
        ("idp0001", "8", "longpress_up_release"),
        ("idp0001", "1", "longpress_down"),
        ("idp0001", "0", "longpress_down_release"),
    ],
)
async def test_commands_and_repeated_telegrams(
    entities, freeathome, datapoint, value, expected
):
    """Every input callback emits its command, including identical repeats."""
    entity = entities[DIMMER_KEY]
    with (
        patch.object(entity, "_trigger_event", wraps=entity._trigger_event) as trigger,
        patch.object(entity, "async_write_ha_state") as write,
    ):
        for _ in range(2):
            await freeathome.update(
                {"datapoints": {f"{SERIAL}/ch0000/{datapoint}": value}}
            )
    assert trigger.call_args_list == [call(expected, {"extra_data": None})] * 2
    assert write.call_count == 2


@pytest.mark.parametrize("reverse", [False, True])
async def test_both_inputs_in_one_message(entities, freeathome, reverse):
    """Write each event before handling the next input, in either input order."""
    entity = entities[DIMMER_KEY]
    datapoints = [("idp0000", "1"), ("idp0001", "9")]
    expected = ["On", "longpress_up"]
    if reverse:
        datapoints.reverse()
        expected.reverse()
    calls = Mock()
    with (
        patch.object(entity, "_trigger_event", wraps=entity._trigger_event) as trigger,
        patch.object(entity, "async_write_ha_state") as write,
    ):
        calls.attach_mock(trigger, "trigger")
        calls.attach_mock(write, "write")
        await freeathome.update(
            {
                "datapoints": {
                    f"{SERIAL}/ch0000/{key}": value for key, value in datapoints
                }
            }
        )
    assert calls.mock_calls == [
        call.trigger(expected[0], {"extra_data": None}),
        call.write(),
        call.trigger(expected[1], {"extra_data": None}),
        call.write(),
    ]


async def test_rapid_sequence_preserves_every_event(hass, entities, freeathome):
    """Real HA state writes retain every event in a burst of telegrams."""
    entity = entities[DIMMER_KEY]
    entity.entity_id = "event.virtual_dimmer"
    observed = []

    @callback
    def record_event(event):
        """Record state changes on the event loop in delivery order."""
        if event.data["entity_id"] == entity.entity_id:
            observed.append(event.data["new_state"].attributes["event_type"])

    unsubscribe = hass.bus.async_listen("state_changed", record_event)
    try:
        for datapoint, value in [
            ("idp0000", "1"),
            ("idp0001", "9"),
            ("idp0001", "9"),
            ("idp0001", "8"),
            ("idp0000", "0"),
            ("idp0001", "1"),
            ("idp0001", "0"),
        ]:
            await freeathome.update(
                {"datapoints": {f"{SERIAL}/ch0000/{datapoint}": value}}
            )
        await hass.async_block_till_done()
        assert observed == [
            "On",
            "longpress_up",
            "longpress_up",
            "longpress_up_release",
            "Off",
            "longpress_down",
            "longpress_down_release",
        ]
    finally:
        unsubscribe()


@pytest.mark.parametrize("value", ["invalid", "7"])
async def test_unknown_dimming_ignored(entities, freeathome, value):
    """Unknown commands do not produce events or duplicate the switching input."""
    entity = entities[DIMMER_KEY]
    with (
        patch.object(entity, "_trigger_event") as trigger,
        patch.object(entity, "async_write_ha_state") as write,
    ):
        await freeathome.update({"datapoints": {f"{SERIAL}/ch0000/idp0001": value}})
    assert entity._channel.requested_dimming_state == "unknown"
    trigger.assert_not_called()
    write.assert_not_called()


async def test_uninitialized_switch_ignored(entities):
    """Missing switching state must not be converted into an Off event."""
    entity = entities[DIMMER_KEY]
    entity._channel._requested_state = None
    with patch.object(entity, "_trigger_event") as trigger:
        entity._async_handle_event()
    trigger.assert_not_called()


async def test_callback_lifecycle(entities):
    """Remove both subscriptions and register exactly once after re-adding."""
    entity = entities[DIMMER_KEY]
    channel = entity._channel
    assert channel._callbacks["requested_state"] == {entity._async_handle_event}
    assert channel._callbacks["requested_dimming_state"] == {
        entity._async_handle_dimming_event
    }
    await entity.async_will_remove_from_hass()
    assert not channel._callbacks["requested_state"]
    assert not channel._callbacks["requested_dimming_state"]
    with patch.object(entity, "_trigger_event") as trigger:
        channel.update_channel("idp0000", "1")
        channel.update_channel("idp0001", "9")
    trigger.assert_not_called()
    await entity.async_added_to_hass()
    assert len(channel._callbacks["requested_state"]) == 1
    assert len(channel._callbacks["requested_dimming_state"]) == 1


async def test_virtual_switch_regression(entities, freeathome):
    """Keep the virtual switch's entity, event types and callback unchanged."""
    entity = entities[SWITCH_KEY]
    assert type(entity._channel) is VirtualSwitchActuator
    assert entity.entity_description.event_types == ["On", "Off"]
    assert entity._channel._callbacks == {
        "requested_state": {entity._async_handle_event}
    }
    with (
        patch.object(entity, "_trigger_event", wraps=entity._trigger_event) as trigger,
        patch.object(entity, "async_write_ha_state") as write,
    ):
        for value in ("1", "1", "0"):
            await freeathome.update({"datapoints": {f"{SERIAL}/ch0001/idp0000": value}})
    assert trigger.call_args_list == [
        call("On", {"extra_data": None}),
        call("On", {"extra_data": None}),
        call("Off", {"extra_data": None}),
    ]
    assert write.call_count == 3


def test_physical_dimming_sensor_description_unchanged():
    """Physical sensors still use their state callback and existing event names."""
    description = EVENT_DESCRIPTIONS["EventDimmingSensorState"]
    assert description["channel_class"] is DimmingSensor
    assert description["state_attribute"] == "state"
    assert description["event_type_callback"]("longpress_up") == "longpress_up"
    assert set(description["entity_description_kwargs"]["event_types"]) == {
        "on",
        "off",
        "unknown",
        *EVENT_TYPES[2:],
    }
