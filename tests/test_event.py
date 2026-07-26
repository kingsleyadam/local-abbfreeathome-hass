"""Test ABB-free@home event platform (doorbell standard ring event)."""

from unittest.mock import MagicMock, Mock, call, patch

from abbfreeathome.channels.des_door_ringing_sensor import DesDoorRingingSensor
from abbfreeathome.channels.virtual.virtual_room_temperature_controller import (
    VirtualRoomTemperatureController,
)

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.event import (
    EVENT_DESCRIPTIONS,
    FreeAtHomeEventEntity,
    async_setup_entry,
)
from homeassistant.components.event import EventDeviceClass
from homeassistant.core import HomeAssistant

DOORBELL_KEY = "EventDesDoorRingingSensorActivated"
TARGET_TEMPERATURE_KEY = "EventVirtualRoomTemperatureControllerTargetTemperature"


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

    assert async_add_entities.call_count == len(EVENT_DESCRIPTIONS)


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
        spec=["channel_name", "channel_id", "register_callback", "remove_callback"]
    )
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

    device_info = entity.device_info
    assert device_info["identifiers"] == {(DOMAIN, "ABB7F57FFFE12345_ch0000")}
    assert device_info["name"] == "Door Ringing Device (ch0000)"
    assert device_info["serial_number"] == "ABB7F57FFFE12345_ch0000"
    assert device_info["hw_version"] == "1234 (sub)"
    assert device_info["suggested_area"] == "Entrance"
    assert device_info["via_device"] == (DOMAIN, "ABB7F57FFFE12345")
