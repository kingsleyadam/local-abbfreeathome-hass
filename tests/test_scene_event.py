"""Test scene events from real library channels through Home Assistant."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, call, patch

from abbfreeathome import FreeAtHome, FreeAtHomeApi
from abbfreeathome.channels.scene import Scene
import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.event import (
    FreeAtHomeSceneEventEntity,
    async_setup_entry,
)
from homeassistant.core import callback

SERIAL = "FFFF4800000A"
DATAPOINT = f"{SERIAL}/ch0000/odp0000"
SCENE_NAME = "Upstairs night lights"
EVENT_DATA = {
    "scene_id": SERIAL,
    "channel_id": "ch0000",
    "scene_name": SCENE_NAME,
    "scene_control": "2",
}


@pytest.fixture
async def freeathome():
    """Load a scene through discovery, including its cached initial value."""
    api = AsyncMock(spec=FreeAtHomeApi)
    # Test live requests after the reconnect snapshot has finished.
    api.is_priming = False
    api.get_configuration.return_value = {
        "devices": {
            SERIAL: {
                "displayName": SCENE_NAME,
                "interface": "scene",
                "channels": {
                    "ch0000": {
                        "displayName": SCENE_NAME,
                        "functionID": "4800",
                        "floor": "02",
                        "room": "0A",
                        "outputs": {"odp0000": {"pairingID": 4, "value": "2"}},
                    }
                },
            }
        },
        "floorplan": {"floors": {}},
    }
    instance = FreeAtHome(api)
    await instance.load()
    return instance


@pytest.fixture
async def entity(hass, mock_config_entry, freeathome):
    """Create the scene entity via platform setup and attach its listener."""
    hass.data[DOMAIN] = {mock_config_entry.entry_id: freeathome}
    added = []
    await async_setup_entry(hass, mock_config_entry, added.extend)
    assert len(added) == 1
    scene_entity = added[0]
    scene_entity.hass = hass
    scene_entity.entity_id = "event.upstairs_night_lights"
    await scene_entity.async_added_to_hass()
    yield scene_entity
    await scene_entity.async_will_remove_from_hass()


async def test_scene_discovery_and_no_initial_event(entity, hass):
    """Discover one named event entity without replaying the cached value."""
    assert type(entity) is FreeAtHomeSceneEventEntity
    assert type(entity._channel) is Scene
    assert entity.name == SCENE_NAME
    assert entity.unique_id == f"{SERIAL}_ch0000_EventSceneRequested"
    assert entity.event_types == ["scene_requested"]
    assert entity.device_info["identifiers"] == {(DOMAIN, SERIAL)}
    entity.async_write_ha_state()
    assert hass.states.get(entity.entity_id).state == "unknown"
    assert hass.states.get(entity.entity_id).attributes.get("event_type") is None


async def test_three_identical_requests(entity, freeathome):
    """Reproduce the three identical scene outputs observed in the SysAP log."""
    with (
        patch.object(entity, "_trigger_event", wraps=entity._trigger_event) as trigger,
        patch.object(entity, "async_write_ha_state") as write,
    ):
        for _ in range(3):
            await freeathome.update(
                {"datapoints": {DATAPOINT: "2"}, "scenesTriggered": {}}
            )
    assert trigger.call_args_list == [call("scene_requested", EVENT_DATA)] * 3
    assert write.call_count == 3


async def test_each_request_reaches_home_assistant(hass, entity, freeathome):
    """Emit a real state change for every request so automations see repeats."""
    observed = []

    @callback
    def record_request(event):
        """Capture the scene event attributes in delivery order."""
        if event.data["entity_id"] == entity.entity_id:
            observed.append(event.data["new_state"].attributes)

    unsubscribe = hass.bus.async_listen("state_changed", record_request)
    try:
        # Physical requests are seconds apart. Explicit timestamps also keep
        # this test deterministic on older HA versions with millisecond states.
        first_request = datetime(2026, 10, 4, 12, 32, 46, tzinfo=UTC)
        for index in range(3):
            with patch(
                "homeassistant.components.event.dt_util.utcnow",
                return_value=first_request + timedelta(seconds=index * 5),
            ):
                await freeathome.update({"datapoints": {DATAPOINT: "2"}})
        await hass.async_block_till_done()
        assert len(observed) == 3
        for attributes in observed:
            assert attributes["event_type"] == "scene_requested"
            for key, value in EVENT_DATA.items():
                assert attributes[key] == value
    finally:
        unsubscribe()


@pytest.mark.parametrize("value", ["", "invalid", "128", "255"])
async def test_invalid_and_learning_values_ignored(entity, freeathome, value):
    """Learning and malformed values cannot trigger a Hue automation."""
    with patch.object(entity, "_trigger_event") as trigger:
        await freeathome.update({"datapoints": {DATAPOINT: value}})
    trigger.assert_not_called()


async def test_scene_listener_lifecycle(entity, freeathome):
    """Unsubscribe on removal and register only once when re-added."""
    channel = entity._channel
    await entity.async_will_remove_from_hass()
    with patch.object(entity, "_trigger_event") as trigger:
        await freeathome.update({"datapoints": {DATAPOINT: "2"}})
    trigger.assert_not_called()
    await entity.async_added_to_hass()
    await entity.async_added_to_hass()
    assert channel._callbacks["scene_control"] == {entity._async_handle_event}


async def test_uninitialized_scene_ignored(entity):
    """Do not manufacture a request when no valid scene-control value exists."""
    entity._channel._scene_control = None
    with patch.object(entity, "_trigger_event") as trigger:
        entity._async_handle_event()
    trigger.assert_not_called()
