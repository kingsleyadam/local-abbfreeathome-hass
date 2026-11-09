"""Test ABB-free@home event platform (doorbell standard ring event)."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

from abbfreeathome.bin.pairing import Pairing
from abbfreeathome.channels.cover_actuator import (
    AtticWindowActuator,
    AwningActuator,
    BlindActuator,
    ShutterActuator,
)
from abbfreeathome.channels.des_door_ringing_sensor import DesDoorRingingSensor
from abbfreeathome.channels.switch_sensor import (
    DimmingSensor,
    StaircaseLightSensor,
    SwitchSensorState,
)
from abbfreeathome.channels.virtual.virtual_room_temperature_controller import (
    VirtualRoomTemperatureController,
)
from abbfreeathome.device import Device
import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.event import (
    EVENT_DESCRIPTIONS,
    FreeAtHomeEventEntity,
    async_setup_entry,
)
from homeassistant.components.event import (
    ATTR_EVENT_TYPES,
    DOMAIN as EVENT_DOMAIN,
    EventDeviceClass,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .common import MockConfigEntry, build_channel, build_device, setup_with_channels

DOORBELL_KEY = "EventDesDoorRingingSensorActivated"
TARGET_TEMPERATURE_KEY = "EventVirtualRoomTemperatureControllerTargetTemperature"
STAIRCASE_KEY = "EventStaircaseLightSensorOnOff"
COVER_CLASSES = (AtticWindowActuator, AwningActuator, BlindActuator, ShutterActuator)


def _build_doorbell_channel() -> Mock:
    """Create a mock DesDoorRingingSensor channel."""
    channel = Mock(
        spec=[
            "channel_name",
            "channel_id",
            "device_serial",
            "device_name",
            "room_name",
            "device",
            "register_callback",
            "remove_callback",
        ]
    )
    channel.channel_name = "Doorbell"
    channel.channel_id = "ch0000"
    channel.device_serial = "ABB7F57FFFE12345"
    channel.device_name = "Door Ringing Device"
    channel.room_name = "Entrance"
    channel.device = Mock()
    channel.device.is_multi_device = False
    return channel


def _build_entity(
    channel: Mock,
    *,
    key: str,
    state_attribute: str,
    event_type_callback,
    extra_data: str | None = None,
    create_subdevices: bool = False,
    event_types: list[str] | None = None,
) -> FreeAtHomeEventEntity:
    """Build an event entity with explicit configuration."""
    return FreeAtHomeEventEntity(
        channel,
        state_attribute=state_attribute,
        entity_description_kwargs={
            "key": key,
            "event_types": event_types or ["ring", "activated"],
        },
        sysap_serial_number="TEST123456",
        create_subdevices=create_subdevices,
        event_type_callback=event_type_callback,
        extra_data=extra_data,
    )


def _build_doorbell_entity(channel: Mock) -> FreeAtHomeEventEntity:
    """Build a doorbell event entity from the platform description."""
    description = EVENT_DESCRIPTIONS[DOORBELL_KEY]
    return FreeAtHomeEventEntity(
        channel,
        state_attribute=description.get("state_attribute"),
        entity_description_kwargs={"key": DOORBELL_KEY}
        | description.get("entity_description_kwargs"),
        sysap_serial_number="TEST123456",
        create_subdevices=False,
        event_type_callback=description.get("event_type_callback"),
        extra_data=description.get("extra_data"),
    )


def test_doorbell_uses_standard_ring_event() -> None:
    """The doorbell entity must expose the standard doorbell class and ring type."""
    description = EVENT_DESCRIPTIONS[DOORBELL_KEY]
    kwargs = description["entity_description_kwargs"]

    assert kwargs["device_class"] == EventDeviceClass.DOORBELL
    assert "ring" in kwargs["event_types"]
    # The legacy "activated" type is retained for backwards compatibility.
    assert "activated" in kwargs["event_types"]
    # The callback fires both the standard "ring" and legacy "activated" types.
    assert description["event_type_callback"]() == ["ring", "activated"]


async def test_async_setup_entry_adds_doorbell(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test the doorbell entity is created with the ring event configuration."""
    mock_config_entry.add_to_hass(hass)

    channel = _build_doorbell_channel()

    mock_free_at_home = MagicMock()
    mock_free_at_home.get_channels_by_class.side_effect = lambda channel_class: (
        [channel] if channel_class is DesDoorRingingSensor else []
    )
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    entities_added = []

    def capture_entities(entity_generator):
        """Capture entities from generator."""
        entities_added.extend(list(entity_generator))

    async_add_entities = MagicMock(side_effect=capture_entities)
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    mock_free_at_home.get_channels_by_class.assert_any_call(
        channel_class=DesDoorRingingSensor
    )

    doorbell = next(
        e for e in entities_added if e.entity_description.key == DOORBELL_KEY
    )
    assert isinstance(doorbell, FreeAtHomeEventEntity)
    assert doorbell.entity_description.device_class == EventDeviceClass.DOORBELL
    assert doorbell.event_types == ["ring", "activated"]
    assert doorbell.unique_id == f"ABB7F57FFFE12345_ch0000_{DOORBELL_KEY}"


def _build_staircase_channel() -> Mock:
    """Create a mock StaircaseLightSensor channel."""
    channel = Mock(
        spec=[
            "channel_name",
            "channel_id",
            "device_serial",
            "device_name",
            "room_name",
            "device",
            "register_callback",
            "remove_callback",
            "state",
        ]
    )
    channel.channel_name = "Gate"
    channel.channel_id = "ch0004"
    channel.device_serial = "ABB7F57FFFE99999"
    channel.device_name = "Gate Device"
    channel.room_name = "Driveway"
    channel.device = Mock()
    channel.device.is_multi_device = False
    return channel


def test_staircase_light_sensor_description() -> None:
    """The staircase-light-sensor event exposes the switch-sensor states."""
    description = EVENT_DESCRIPTIONS[STAIRCASE_KEY]
    kwargs = description["entity_description_kwargs"]

    assert description["channel_class"] is StaircaseLightSensor
    assert kwargs["device_class"] == EventDeviceClass.BUTTON
    assert kwargs["translation_key"] == "staircase_light_sensor"
    assert set(kwargs["event_types"]) == {state.name for state in SwitchSensorState}
    assert description["event_type_callback"]("on") == "on"


async def test_dimming_sensor_event_types_order(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test the dimming sensor lists its event types in a fixed order."""
    monkeypatch.setattr(
        "custom_components.abbfreeathome_ci.PLATFORMS", [Platform.EVENT]
    )
    channel = build_channel(
        DimmingSensor,
        build_device(),
        outputs={
            Pairing.AL_SWITCH_ON_OFF: "0",
            Pairing.AL_RELATIVE_SET_VALUE_CONTROL: "0",
        },
    )
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )

    entity_id = entity_registry.async_get_entity_id(
        EVENT_DOMAIN, DOMAIN, "ABB700000001_ch0000_EventDimmingSensorState"
    )
    # The switch sensor states, then the dimming states not among them.
    assert hass.states.get(entity_id).attributes[ATTR_EVENT_TYPES] == [
        "unknown",
        "off",
        "on",
        "longpress_up",
        "longpress_up_release",
        "longpress_down",
        "longpress_down_release",
    ]


async def test_async_setup_entry_adds_staircase_light_sensor(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test the staircase-light-sensor entity is created for its channel."""
    mock_config_entry.add_to_hass(hass)

    channel = _build_staircase_channel()

    mock_free_at_home = MagicMock()
    mock_free_at_home.get_channels_by_class.side_effect = lambda channel_class: (
        [channel] if channel_class is StaircaseLightSensor else []
    )
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    entities_added = []

    def capture_entities(entity_generator):
        """Capture entities from generator."""
        entities_added.extend(list(entity_generator))

    async_add_entities = MagicMock(side_effect=capture_entities)
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    mock_free_at_home.get_channels_by_class.assert_any_call(
        channel_class=StaircaseLightSensor
    )

    staircase = next(
        e for e in entities_added if e.entity_description.key == STAIRCASE_KEY
    )
    assert isinstance(staircase, FreeAtHomeEventEntity)
    assert staircase.entity_description.device_class == EventDeviceClass.BUTTON
    assert staircase.unique_id == f"ABB7F57FFFE99999_ch0004_{STAIRCASE_KEY}"


async def test_async_setup_entry_no_channels(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup adds one call per description when no channels exist."""
    mock_config_entry.add_to_hass(hass)

    mock_free_at_home = MagicMock()
    mock_free_at_home.get_channels_by_class.return_value = []
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    async_add_entities = MagicMock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert async_add_entities.call_count == 1


async def test_async_setup_entry_builds_entity_with_extra_data(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup constructs an entity for a description carrying extra_data."""
    mock_config_entry.add_to_hass(hass)

    channel = Mock(
        spec=[
            "channel_name",
            "channel_id",
            "device_serial",
            "device_name",
            "room_name",
            "device",
        ]
    )
    channel.channel_name = "Thermostat"
    channel.channel_id = "ch0001"
    channel.device_serial = "ABB7F57FFFE54321"
    channel.device_name = "Thermostat Device"
    channel.room_name = "Living Room"
    channel.device = Mock()
    channel.device.is_multi_device = False

    mock_free_at_home = MagicMock()
    mock_free_at_home.get_channels_by_class.side_effect = lambda channel_class: (
        [channel] if channel_class is VirtualRoomTemperatureController else []
    )
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    entities_added = []

    def capture_entities(entity_generator):
        """Capture entities from generator."""
        entities_added.extend(list(entity_generator))

    async_add_entities = MagicMock(side_effect=capture_entities)
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    target_temperature = next(
        e for e in entities_added if e.entity_description.key == TARGET_TEMPERATURE_KEY
    )
    assert target_temperature._extra_data == "requested_target_temperature"


def test_doorbell_fires_ring_and_activated_events() -> None:
    """A doorbell press fires both the standard ring and legacy activated types."""
    channel = _build_doorbell_channel()
    entity = _build_doorbell_entity(channel)

    with (
        patch.object(entity, "_trigger_event") as mock_trigger,
        patch.object(entity, "async_write_ha_state") as mock_write,
    ):
        entity._async_handle_event()

    assert mock_trigger.call_args_list == [
        call("ring", {"extra_data": None}),
        call("activated", {"extra_data": None}),
    ]
    assert mock_write.call_count == 2


def test_handle_event_with_state_attribute() -> None:
    """A callback reading a state attribute fires a single event type."""
    channel = Mock(spec=["channel_name", "channel_id", "state"])
    channel.channel_name = "Switch"
    channel.channel_id = "ch0002"
    channel.state = "On"

    entity = _build_entity(
        channel,
        key="switch",
        state_attribute="state",
        event_type_callback=lambda state: state,
        event_types=["On", "Off"],
    )

    with (
        patch.object(entity, "_trigger_event") as mock_trigger,
        patch.object(entity, "async_write_ha_state") as mock_write,
    ):
        entity._async_handle_event()

    mock_trigger.assert_called_once_with("On", {"extra_data": None})
    mock_write.assert_called_once()


def test_handle_event_with_extra_data() -> None:
    """A callback with extra_data forwards the channel attribute value."""
    channel = Mock(spec=["channel_name", "channel_id", "requested_target_temperature"])
    channel.channel_name = "Thermostat"
    channel.channel_id = "ch0003"
    channel.requested_target_temperature = 21.5

    entity = _build_entity(
        channel,
        key=TARGET_TEMPERATURE_KEY,
        state_attribute="requested_target_temperature",
        event_type_callback=lambda value: "requested_target_temperature",
        extra_data="requested_target_temperature",
        event_types=["requested_target_temperature"],
    )

    with (
        patch.object(entity, "_trigger_event") as mock_trigger,
        patch.object(entity, "async_write_ha_state"),
    ):
        entity._async_handle_event()

    mock_trigger.assert_called_once_with(
        "requested_target_temperature", {"extra_data": 21.5}
    )


async def test_callbacks_registered_with_state_attribute() -> None:
    """Callbacks register/remove using a non-empty state attribute."""
    channel = Mock(
        spec=[
            "channel_name",
            "channel_id",
            "device",
            "register_callback",
            "remove_callback",
        ]
    )
    channel.device = Mock()
    channel.channel_name = "Switch"
    channel.channel_id = "ch0004"

    entity = _build_entity(
        channel,
        key="switch",
        state_attribute="requested_state",
        event_type_callback=lambda state: "On",
    )

    await entity.async_added_to_hass()
    channel.register_callback.assert_called_once_with(
        callback_attribute="requested_state", callback=entity._async_handle_event
    )

    await entity.async_will_remove_from_hass()
    channel.remove_callback.assert_called_once_with(
        callback_attribute="requested_state", callback=entity._async_handle_event
    )


async def test_callbacks_registered_without_state_attribute() -> None:
    """Callbacks fall back to the "state" attribute when none is provided."""
    channel = _build_doorbell_channel()
    entity = _build_doorbell_entity(channel)

    await entity.async_added_to_hass()
    channel.register_callback.assert_called_once_with(
        callback_attribute="state", callback=entity._async_handle_event
    )

    await entity.async_will_remove_from_hass()
    channel.remove_callback.assert_called_once_with(
        callback_attribute="state", callback=entity._async_handle_event
    )


def test_device_info_default() -> None:
    """A non-multi device returns identifiers keyed on the device serial."""
    channel = _build_doorbell_channel()
    entity = _build_doorbell_entity(channel)

    assert entity.device_info["identifiers"] == {(DOMAIN, "ABB7F57FFFE12345")}


def test_device_info_subdevice() -> None:
    """A multi device with subdevices enabled returns a per-channel device."""
    channel = _build_doorbell_channel()
    channel.device.is_multi_device = True
    channel.device.device_id = "1234"

    entity = _build_entity(
        channel,
        key=DOORBELL_KEY,
        state_attribute="",
        event_type_callback=lambda: ["ring", "activated"],
        create_subdevices=True,
    )

    entity.platform = MagicMock()
    with patch(
        "custom_components.abbfreeathome_ci.event.async_get_sub_device_info"
    ) as mock_sub_device_info:
        device_info = entity.device_info

    mock_sub_device_info.assert_called_once_with(
        entity.hass, entity.platform.config_entry.entry_id, channel
    )
    assert device_info is mock_sub_device_info.return_value


def _build_cover_channel(channel_class: type, position: str = "") -> Any:
    """Create a real library cover channel with a requested position input."""
    device = Device(
        device_serial="ABB7F57FFFE77777",
        device_id="B001",
        display_name="Skylight Cover",
        api=Mock(set_datapoint=AsyncMock(), get_datapoint=AsyncMock()),
    )
    return channel_class(
        device=device,
        channel_id="ch0000",
        channel_name="Skylight Cover",
        inputs={
            "idp0000": {
                "pairingID": Pairing.AL_SET_ABSOLUTE_POSITION_BLINDS_PERCENTAGE.value,
                "value": position,
            },
        },
        outputs={
            "odp0001": {
                "pairingID": Pairing.AL_CURRENT_ABSOLUTE_POSITION_BLINDS_PERCENTAGE.value,
                "value": "100",
            },
        },
        parameters={},
    )


def _build_cover_entity(channel: Any) -> FreeAtHomeEventEntity:
    """Build a requested-position event entity from the platform description."""
    key = f"Event{type(channel).__name__}RequestedPosition"
    description = EVENT_DESCRIPTIONS[key]
    return FreeAtHomeEventEntity(
        channel,
        state_attribute=description["state_attribute"],
        entity_description_kwargs={"key": key}
        | description["entity_description_kwargs"],
        sysap_serial_number="TEST123456",
        create_subdevices=False,
        event_type_callback=description["event_type_callback"],
        extra_data=description["extra_data"],
        extra_data_callback=description["extra_data_callback"],
    )


async def test_async_setup_entry_adds_cover_requested_position(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Every cover class gets a requested-position event entity."""
    mock_config_entry.add_to_hass(hass)
    channels = {cls: _build_cover_channel(cls) for cls in COVER_CLASSES}

    mock_free_at_home = MagicMock()
    mock_free_at_home.get_channels_by_class.side_effect = lambda channel_class: (
        [channels[channel_class]] if channel_class in channels else []
    )
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    entities_added = []
    await async_setup_entry(hass, mock_config_entry, entities_added.extend)

    covers = [
        e for e in entities_added if e.entity_description.key.endswith("Position")
    ]
    assert {e.unique_id for e in covers} == {
        f"ABB7F57FFFE77777_ch0000_Event{cls.__name__}RequestedPosition"
        for cls in COVER_CLASSES
    }
    assert all(e.event_types == ["requested_position"] for e in covers)
    assert all(
        e.entity_description.translation_key == "cover_actuator_requested_position"
        for e in covers
    )


@pytest.mark.parametrize(
    ("channel_class", "value", "expected"),
    [
        (BlindActuator, "30", 70),
        (ShutterActuator, "0", 100),
        (AtticWindowActuator, "100", 0),
        # The library inverts awnings; the event matches the cover entity.
        (AwningActuator, "30", 30),
    ],
)
async def test_cover_requested_position_events(
    channel_class: type, value: str, expected: int
) -> None:
    """Requests, including repeats, fire with a Home Assistant position."""
    channel = _build_cover_channel(channel_class)
    entity = _build_cover_entity(channel)
    entity.async_write_ha_state = Mock()
    await entity.async_added_to_hass()

    with patch.object(entity, "_trigger_event") as trigger:
        channel.update_channel("idp0000", value)
        channel.update_channel("idp0000", value)
        channel.update_channel("idp0000", "invalid")

    assert trigger.call_args_list == [
        call("requested_position", {"extra_data": expected}),
        call("requested_position", {"extra_data": expected}),
    ]
    assert entity.async_write_ha_state.call_count == 2

    await entity.async_will_remove_from_hass()
    assert not channel._callbacks["target_position"]


async def test_cover_requested_position_ignores_feedback() -> None:
    """Position feedback does not fire a requested-position event."""
    channel = _build_cover_channel(BlindActuator, position="40")
    entity = _build_cover_entity(channel)
    entity.async_write_ha_state = Mock()
    await entity.async_added_to_hass()

    with patch.object(entity, "_trigger_event") as trigger:
        channel.update_channel("odp0001", "50")

    trigger.assert_not_called()
    assert channel.target_position == 40


@pytest.mark.parametrize(
    ("command", "raw", "expected"), [("open", "100", 100), ("close", "0", 0)]
)
async def test_awning_open_close_fire_requested_position(
    command: str, raw: str, expected: int
) -> None:
    """Awning open/close send an absolute position, so their echo fires an event."""
    channel = _build_cover_channel(AwningActuator)
    entity = _build_cover_entity(channel)
    entity.async_write_ha_state = Mock()
    await entity.async_added_to_hass()

    with patch.object(entity, "_trigger_event") as trigger:
        await getattr(channel, command)()
        channel.device.api.set_datapoint.assert_awaited_once_with(
            device_serial="ABB7F57FFFE77777",
            channel_id="ch0000",
            datapoint="idp0000",
            value=raw,
        )
        trigger.assert_not_called()
        channel.update_channel("idp0000", raw)

    trigger.assert_called_once_with("requested_position", {"extra_data": expected})
