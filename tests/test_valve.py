"""Test ABB-free@home valve."""

from unittest.mock import AsyncMock, MagicMock

from abbfreeathome.channels.valve_actuator import (
    CoolingActuator,
    HeatingActuator,
    HeatingCoolingActuator,
)

from custom_components.abbfreeathome_ci.const import DOMAIN
from custom_components.abbfreeathome_ci.valve import (
    FreeAtHomeValveEntity,
    async_setup_entry,
)
from homeassistant.components.valve import ValveDeviceClass, ValveEntityFeature
from homeassistant.core import HomeAssistant


async def test_async_setup_entry_no_valves(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup with no valve entities."""
    mock_config_entry.add_to_hass(hass)

    mock_free_at_home = MagicMock()
    mock_free_at_home.get_channels_by_class.return_value = []
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    async_add_entities = MagicMock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # Should be called 4 times (once per valve description)
    assert async_add_entities.call_count == 4


async def test_async_setup_entry_with_heating_actuator(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup with a heating actuator."""
    mock_config_entry.add_to_hass(hass)

    # Create a mock heating actuator channel
    mock_channel = MagicMock()
    mock_channel.channel_name = "Floor Heating"
    mock_channel.channel_id = "ch0000"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.device_name = "Heating Device"
    mock_channel.room_name = "Living Room"
    mock_channel.position = 75
    mock_channel.device.is_multi_device = False

    mock_free_at_home = MagicMock()

    def get_channels_by_class_side_effect(channel_class):
        """Return channels only for HeatingActuator."""
        if channel_class == HeatingActuator:
            return [mock_channel]
        return []

    mock_free_at_home.get_channels_by_class.side_effect = (
        get_channels_by_class_side_effect
    )
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    entities_added = []

    def capture_entities(entity_generator):
        """Capture entities from generator."""
        entities = list(entity_generator)
        entities_added.extend(entities)

    async_add_entities = MagicMock(side_effect=capture_entities)
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # Should have added 1 entity
    assert len(entities_added) == 1
    entity = entities_added[0]

    assert isinstance(entity, FreeAtHomeValveEntity)
    assert entity.entity_description.name == "Floor Heating"
    # Backward compatible unique_id format
    assert entity.unique_id == "ABB7F57FFFE12345_ch0000_valve"
    assert entity.current_valve_position == 75


async def test_async_setup_entry_with_cooling_actuator(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup with a cooling actuator."""
    mock_config_entry.add_to_hass(hass)

    mock_channel = MagicMock()
    mock_channel.channel_name = "Floor Cooling"
    mock_channel.channel_id = "ch0001"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.device_name = "Cooling Device"
    mock_channel.room_name = "Bedroom"
    mock_channel.position = 50
    mock_channel.device.is_multi_device = False

    mock_free_at_home = MagicMock()

    def get_channels_by_class_side_effect(channel_class):
        """Return channels only for CoolingActuator."""
        if channel_class == CoolingActuator:
            return [mock_channel]
        return []

    mock_free_at_home.get_channels_by_class.side_effect = (
        get_channels_by_class_side_effect
    )
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    entities_added = []

    def capture_entities(entity_generator):
        """Capture entities from generator."""
        entities = list(entity_generator)
        entities_added.extend(entities)

    async_add_entities = MagicMock(side_effect=capture_entities)
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert len(entities_added) == 1
    entity = entities_added[0]

    assert isinstance(entity, FreeAtHomeValveEntity)
    assert entity.entity_description.name == "Floor Cooling"
    assert entity.unique_id == "ABB7F57FFFE12345_ch0001_CoolingActuatorValve"
    assert entity.current_valve_position == 50


async def test_async_setup_entry_with_heating_cooling_actuator(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test setup with a heating/cooling actuator creates two entities."""
    mock_config_entry.add_to_hass(hass)

    mock_channel = MagicMock()
    mock_channel.channel_name = "Climate Control"
    mock_channel.channel_id = "ch0002"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.device_name = "Climate Device"
    mock_channel.room_name = "Office"
    mock_channel.heating_position = 80
    mock_channel.cooling_position = 20
    mock_channel.device.is_multi_device = False

    mock_free_at_home = MagicMock()

    def get_channels_by_class_side_effect(channel_class):
        """Return channels only for HeatingCoolingActuator."""
        if channel_class == HeatingCoolingActuator:
            return [mock_channel]
        return []

    mock_free_at_home.get_channels_by_class.side_effect = (
        get_channels_by_class_side_effect
    )
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    entities_added = []

    def capture_entities(entity_generator):
        """Capture entities from generator."""
        entities = list(entity_generator)
        entities_added.extend(entities)

    async_add_entities = MagicMock(side_effect=capture_entities)
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # Should have added 2 entities (heating and cooling)
    assert len(entities_added) == 2

    # Verify both entities are present with correct keys
    entity_keys = [e.entity_description.key for e in entities_added]
    assert "HeatingCoolingActuatorHeatingValve" in entity_keys
    assert "HeatingCoolingActuatorCoolingValve" in entity_keys

    # Find heating and cooling entities
    heating_entity = next(
        e
        for e in entities_added
        if e.entity_description.key == "HeatingCoolingActuatorHeatingValve"
    )
    cooling_entity = next(
        e
        for e in entities_added
        if e.entity_description.key == "HeatingCoolingActuatorCoolingValve"
    )

    # Check heating entity
    assert heating_entity.entity_description.name == "Climate Control"
    assert (
        heating_entity.unique_id
        == "ABB7F57FFFE12345_ch0002_HeatingCoolingActuatorHeatingValve"
    )
    assert heating_entity.current_valve_position == 80

    # Check cooling entity
    assert cooling_entity.entity_description.name == "Climate Control"
    assert (
        cooling_entity.unique_id
        == "ABB7F57FFFE12345_ch0002_HeatingCoolingActuatorCoolingValve"
    )
    assert cooling_entity.current_valve_position == 20


async def test_heating_valve_entity_properties(hass: HomeAssistant) -> None:
    """Test heating valve entity properties."""
    mock_channel = MagicMock(spec=HeatingActuator)
    mock_channel.channel_name = "Test Heating"
    mock_channel.channel_id = "ch0003"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.device_name = "Heating Device"
    mock_channel.room_name = "Kitchen"
    mock_channel.position = 65
    mock_channel.device.is_multi_device = False

    entity = FreeAtHomeValveEntity(
        channel=mock_channel,
        position_attribute="position",
        set_position_method="set_position",
        callback_attributes=["position"],
        entity_description_kwargs={
            "key": "HeatingActuatorValve",
            "device_class": ValveDeviceClass.WATER,
            "translation_key": "heating_actuator",
        },
        sysap_serial_number="TEST123456",
        create_subdevices=False,
    )

    assert entity.entity_description.name == "Test Heating"
    assert entity.entity_description.key == "HeatingActuatorValve"
    assert entity.entity_description.device_class == ValveDeviceClass.WATER
    assert entity.unique_id == "ABB7F57FFFE12345_ch0003_valve"  # Backward compatible
    assert entity.current_valve_position == 65
    assert entity.should_poll is False
    assert entity.supported_features == ValveEntityFeature.SET_POSITION

    # Test device info
    device_info = entity.device_info
    assert device_info["identifiers"] == {(DOMAIN, "ABB7F57FFFE12345")}


async def test_cooling_valve_entity_properties(hass: HomeAssistant) -> None:
    """Test cooling valve entity properties."""
    mock_channel = MagicMock(spec=CoolingActuator)
    mock_channel.channel_name = "Test Cooling"
    mock_channel.channel_id = "ch0004"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.device_name = "Cooling Device"
    mock_channel.room_name = "Basement"
    mock_channel.position = 30
    mock_channel.device.is_multi_device = False

    entity = FreeAtHomeValveEntity(
        channel=mock_channel,
        position_attribute="position",
        set_position_method="set_position",
        callback_attributes=["position"],
        entity_description_kwargs={
            "key": "CoolingActuatorValve",
            "device_class": ValveDeviceClass.WATER,
            "translation_key": "cooling_actuator",
        },
        sysap_serial_number="TEST123456",
        create_subdevices=False,
    )

    assert entity.entity_description.name == "Test Cooling"
    assert entity.unique_id == "ABB7F57FFFE12345_ch0004_CoolingActuatorValve"
    assert entity.current_valve_position == 30


async def test_valve_entity_with_subdevices(hass: HomeAssistant) -> None:
    """Test valve entity with subdevices enabled."""
    mock_channel = MagicMock(spec=HeatingActuator)
    mock_channel.channel_name = "Zone 1 Heating"
    mock_channel.channel_id = "ch0005"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.device_name = "Multi Zone Heating"
    mock_channel.room_name = "Zone 1"
    mock_channel.position = 90
    mock_channel.device.is_multi_device = True
    mock_channel.device.device_id = "5678"

    entity = FreeAtHomeValveEntity(
        channel=mock_channel,
        position_attribute="position",
        set_position_method="set_position",
        callback_attributes=["position"],
        entity_description_kwargs={
            "key": "HeatingActuatorValve",
            "device_class": ValveDeviceClass.WATER,
            "translation_key": "heating_actuator",
        },
        sysap_serial_number="TEST123456",
        create_subdevices=True,
    )

    # Test device info for subdevice
    device_info = entity.device_info
    assert device_info["identifiers"] == {(DOMAIN, "ABB7F57FFFE12345_ch0005")}
    assert device_info["name"] == "Multi Zone Heating (ch0005)"
    assert device_info["serial_number"] == "ABB7F57FFFE12345_ch0005"
    assert device_info["hw_version"] == "5678 (sub)"
    assert device_info["suggested_area"] == "Zone 1"
    assert device_info["via_device"] == (DOMAIN, "ABB7F57FFFE12345")


async def test_valve_entity_callbacks(hass: HomeAssistant) -> None:
    """Test valve entity callback registration."""
    mock_channel = MagicMock(spec=HeatingActuator)
    mock_channel.channel_name = "Test Valve"
    mock_channel.channel_id = "ch0006"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.position = 50

    entity = FreeAtHomeValveEntity(
        channel=mock_channel,
        position_attribute="position",
        set_position_method="set_position",
        callback_attributes=["position"],
        entity_description_kwargs={
            "key": "HeatingActuatorValve",
            "device_class": ValveDeviceClass.WATER,
            "translation_key": "heating_actuator",
        },
        sysap_serial_number="TEST123456",
        create_subdevices=False,
    )

    # Mock the async_write_ha_state method
    entity.async_write_ha_state = MagicMock()

    # Test callback registration on add
    await entity.async_added_to_hass()
    mock_channel.register_callback.assert_called_once_with(
        callback_attribute="position",
        callback=entity.async_write_ha_state,
    )

    # Test callback removal
    await entity.async_will_remove_from_hass()
    mock_channel.remove_callback.assert_called_once_with(
        callback_attribute="position",
        callback=entity.async_write_ha_state,
    )


async def test_heating_cooling_valve_callbacks(hass: HomeAssistant) -> None:
    """Test heating/cooling valve entity registers multiple callbacks."""
    mock_channel = MagicMock(spec=HeatingCoolingActuator)
    mock_channel.channel_name = "Test Climate"
    mock_channel.channel_id = "ch0007"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.heating_position = 70
    mock_channel.cooling_position = 30

    entity = FreeAtHomeValveEntity(
        channel=mock_channel,
        position_attribute="heating_position",
        set_position_method="set_heating_position",
        callback_attributes=["heating_position", "cooling_position"],
        entity_description_kwargs={
            "key": "HeatingCoolingActuatorHeatingValve",
            "device_class": ValveDeviceClass.WATER,
            "translation_key": "heating_actuator",
        },
        sysap_serial_number="TEST123456",
        create_subdevices=False,
    )

    entity.async_write_ha_state = MagicMock()

    # Test callback registration - should register for both attributes
    await entity.async_added_to_hass()
    assert mock_channel.register_callback.call_count == 2

    # Test callback removal
    await entity.async_will_remove_from_hass()
    assert mock_channel.remove_callback.call_count == 2


async def test_valve_entity_set_position(hass: HomeAssistant) -> None:
    """Test valve entity set position action."""
    mock_channel = MagicMock(spec=HeatingActuator)
    mock_channel.channel_name = "Test Valve"
    mock_channel.channel_id = "ch0008"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.position = 50
    mock_channel.set_position = AsyncMock()

    entity = FreeAtHomeValveEntity(
        channel=mock_channel,
        position_attribute="position",
        set_position_method="set_position",
        callback_attributes=["position"],
        entity_description_kwargs={
            "key": "HeatingActuatorValve",
            "device_class": ValveDeviceClass.WATER,
            "translation_key": "heating_actuator",
        },
        sysap_serial_number="TEST123456",
        create_subdevices=False,
    )

    # Test setting position
    await entity.async_set_valve_position(75)
    mock_channel.set_position.assert_called_once_with(75)


async def test_heating_cooling_valve_set_position(hass: HomeAssistant) -> None:
    """Test heating/cooling valve calls correct set method."""
    mock_channel = MagicMock(spec=HeatingCoolingActuator)
    mock_channel.channel_name = "Test Climate"
    mock_channel.channel_id = "ch0009"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.heating_position = 80
    mock_channel.cooling_position = 20
    mock_channel.set_heating_position = AsyncMock()
    mock_channel.set_cooling_position = AsyncMock()

    # Test heating entity
    heating_entity = FreeAtHomeValveEntity(
        channel=mock_channel,
        position_attribute="heating_position",
        set_position_method="set_heating_position",
        callback_attributes=["heating_position"],
        entity_description_kwargs={
            "key": "HeatingCoolingActuatorHeatingValve",
            "device_class": ValveDeviceClass.WATER,
            "translation_key": "heating_actuator",
        },
        sysap_serial_number="TEST123456",
        create_subdevices=False,
    )

    await heating_entity.async_set_valve_position(85)
    mock_channel.set_heating_position.assert_called_once_with(85)

    # Test cooling entity
    cooling_entity = FreeAtHomeValveEntity(
        channel=mock_channel,
        position_attribute="cooling_position",
        set_position_method="set_cooling_position",
        callback_attributes=["cooling_position"],
        entity_description_kwargs={
            "key": "HeatingCoolingActuatorCoolingValve",
            "device_class": ValveDeviceClass.WATER,
            "translation_key": "heating_cooling_actuator_cooling",
        },
        sysap_serial_number="TEST123456",
        create_subdevices=False,
    )

    await cooling_entity.async_set_valve_position(25)
    mock_channel.set_cooling_position.assert_called_once_with(25)


async def test_valve_entity_position_changes(hass: HomeAssistant) -> None:
    """Test valve entity reflects channel position changes."""
    mock_channel = MagicMock(spec=HeatingActuator)
    mock_channel.channel_name = "Dynamic Valve"
    mock_channel.channel_id = "ch0010"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.position = 40

    entity = FreeAtHomeValveEntity(
        channel=mock_channel,
        position_attribute="position",
        set_position_method="set_position",
        callback_attributes=["position"],
        entity_description_kwargs={
            "key": "HeatingActuatorValve",
            "device_class": ValveDeviceClass.WATER,
            "translation_key": "heating_actuator",
        },
        sysap_serial_number="TEST123456",
        create_subdevices=False,
    )

    # Initial position
    assert entity.current_valve_position == 40

    # Change channel position
    mock_channel.position = 60
    assert entity.current_valve_position == 60

    # Change back
    mock_channel.position = 25
    assert entity.current_valve_position == 25


async def test_valve_entity_update(hass: HomeAssistant) -> None:
    """Test valve entity update method."""
    mock_channel = MagicMock(spec=HeatingActuator)
    mock_channel.channel_name = "Test Valve"
    mock_channel.channel_id = "ch0011"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.position = 50
    mock_channel.refresh_state = AsyncMock()

    entity = FreeAtHomeValveEntity(
        channel=mock_channel,
        position_attribute="position",
        set_position_method="set_position",
        callback_attributes=["position"],
        entity_description_kwargs={
            "key": "HeatingActuatorValve",
            "device_class": ValveDeviceClass.WATER,
            "translation_key": "heating_actuator",
        },
        sysap_serial_number="TEST123456",
        create_subdevices=False,
    )

    # Test update
    await entity.async_update()
    mock_channel.refresh_state.assert_called_once()


async def test_valve_entity_description_attributes(hass: HomeAssistant) -> None:
    """Test valve entity description attributes."""
    mock_channel = MagicMock(spec=HeatingActuator)
    mock_channel.channel_name = "Test Valve"
    mock_channel.channel_id = "ch0012"
    mock_channel.device_serial = "ABB7F57FFFE12345"
    mock_channel.position = 50

    entity = FreeAtHomeValveEntity(
        channel=mock_channel,
        position_attribute="position",
        set_position_method="set_position",
        callback_attributes=["position"],
        entity_description_kwargs={
            "key": "HeatingActuatorValve",
            "device_class": ValveDeviceClass.WATER,
            "translation_key": "heating_actuator",
        },
        sysap_serial_number="TEST123456",
        create_subdevices=False,
    )

    assert entity.entity_description.key == "HeatingActuatorValve"
    assert entity.entity_description.device_class == ValveDeviceClass.WATER
    assert entity.entity_description.translation_key == "heating_actuator"
    assert entity.entity_description.has_entity_name is True
    assert entity.entity_description.name == "Test Valve"
    assert entity.entity_description.entity_registry_enabled_default is False
    assert entity.entity_description.reports_position is True
