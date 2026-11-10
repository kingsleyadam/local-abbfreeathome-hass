"""Test ABB-free@home climate."""

from collections.abc import Callable, Mapping
from runpy import run_path
from typing import Any
from unittest.mock import MagicMock, call

from abbfreeathome.bin.function import Function
from abbfreeathome.bin.pairing import Pairing
from abbfreeathome.channels.room_temperature_controller import (
    RadiatorActuator,
    RoomTemperatureController,
)
from abbfreeathome.const import FUNCTION_CHANNEL_MAPPING
from abbfreeathome.device import Device
import pytest
from syrupy.assertion import SnapshotAssertion

from custom_components.abbfreeathome_ci import climate as climate_platform
from custom_components.abbfreeathome_ci.const import CONF_CREATE_SUBDEVICES, DOMAIN
from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntity,
    HVACAction,
    HVACMode,
)
from homeassistant.components.homeassistant import (
    DOMAIN as HOMEASSISTANT_DOMAIN,
    SERVICE_UPDATE_ENTITY,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    Platform,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util.unit_system import (
    METRIC_SYSTEM,
    US_CUSTOMARY_SYSTEM,
    UnitSystem,
)

from .common import (
    MockConfigEntry,
    build_channel,
    build_device,
    setup_with_channels,
    snapshot_entities,
)

SERIAL = "ABB700000001"
RTC = "ch0000"
RADIATOR = "ch0001"

# Both channels take commands on the same inputs: switching on and off on
# idp0000, eco mode on idp0001, and the target temperature on idp0002.
INPUTS = {
    Pairing.AL_CONTROLLER_ON_OFF_REQUEST: "0",
    Pairing.AL_ECO_ON_OFF: "0",
    Pairing.AL_INFO_ABSOLUTE_SET_POINT_REQUEST: "21",
}
# Switched on in comfort and heating mode (0x21), heating or cooling allowed;
# 0x04 adds eco mode, 0x40 forbids heating and cooling, and without 0x20 the
# controller is in cooling mode.
RTC_OUTPUTS = {
    Pairing.AL_CONTROLLER_ON_OFF: "1",
    Pairing.AL_SET_POINT_TEMPERATURE: "21",
    Pairing.AL_MEASURED_TEMPERATURE: "21.3",
    Pairing.AL_STATE_INDICATION: "33",
    Pairing.AL_ACTUATING_VALUE_HEATING: "0",
    Pairing.AL_ACTUATING_VALUE_COOLING: "0",
}
RADIATOR_OUTPUTS = {
    Pairing.AL_CONTROLLER_ON_OFF: "1",
    Pairing.AL_SET_POINT_TEMPERATURE: "21.5",
    Pairing.AL_MEASURED_TEMPERATURE: "20.4",
    Pairing.AL_STATE_INDICATION: "33",
    Pairing.AL_HEATING_ACTIVE: "0",
    Pairing.AL_HEATING_DEMAND: "0",
}


@pytest.fixture(autouse=True)
def climate_platform_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load only the climate platform."""
    monkeypatch.setattr(
        "custom_components.abbfreeathome_ci.PLATFORMS", [Platform.CLIMATE]
    )


def _outputs(
    defaults: Mapping[Pairing, str], overrides: Mapping[Pairing, str | None]
) -> dict[Pairing, str]:
    """Return outputs with overridden values; None leaves an output out."""
    outputs = {**defaults, **overrides}
    return {pairing: value for pairing, value in outputs.items() if value is not None}


def _build_rtc(
    device: Device,
    channel_id: str = RTC,
    outputs: Mapping[Pairing, str | None] | None = None,
) -> RoomTemperatureController:
    """Build a real room temperature controller, idle in heating mode."""
    return build_channel(
        RoomTemperatureController,
        device,
        channel_id,
        inputs=INPUTS,
        outputs=_outputs(RTC_OUTPUTS, outputs or {}),
    )


def _build_radiator(
    device: Device,
    channel_id: str = RADIATOR,
    outputs: Mapping[Pairing, str | None] | None = None,
) -> RadiatorActuator:
    """Build a real radiator thermostat, idle in heating mode."""
    return build_channel(
        RadiatorActuator,
        device,
        channel_id,
        inputs=INPUTS,
        outputs=_outputs(RADIATOR_OUTPUTS, outputs or {}),
    )


def _report(channel: RoomTemperatureController, pairing: Pairing, value: str) -> None:
    """Report the value of the channel's output with the pairing, as the SysAP."""
    datapoint, _ = channel.get_output_by_pairing(pairing)
    channel.update_channel(
        f"{channel.device_serial}/{channel.channel_id}/{datapoint}", value
    )


def _entity_id(entity_registry: er.EntityRegistry, channel_id: str) -> str:
    """Return the entity ID of the climate entity of a channel by its unique ID."""
    entity_id = entity_registry.async_get_entity_id(
        CLIMATE_DOMAIN, DOMAIN, f"{SERIAL}_{channel_id}_climate"
    )
    assert entity_id is not None
    return entity_id


def _set_datapoint(channel_id: str, datapoint: str, value: str) -> Any:
    """Return the expected call to set an input datapoint of a channel."""
    return call(
        device_serial=SERIAL, channel_id=channel_id, datapoint=datapoint, value=value
    )


async def test_climate_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the climate entities of a controller and a radiator thermostat."""
    device = build_device(SERIAL)
    await setup_with_channels(
        hass,
        mock_config_entry,
        mock_free_at_home_settings,
        [_build_rtc(device), _build_radiator(device)],
    )

    snapshot_entities(hass, snapshot, mock_config_entry.entry_id)


@pytest.mark.parametrize(
    ("state_indication", "heating", "cooling", "expected"),
    [
        # Without a state indication, the larger actuating value wins.
        (None, "0", "0", HVACAction.IDLE),
        (None, "40", "0", HVACAction.HEATING),
        (None, "0", "40", HVACAction.COOLING),
        (None, "40", "40", HVACAction.IDLE),
        # Heating or cooling forbidden (0x40): the actuating values are not
        # carried out.
        ("97", "0", "100", HVACAction.IDLE),
        ("65", "0", "100", HVACAction.IDLE),
        # Otherwise only the actuating value of the indicated mode counts.
        ("33", "18", "0", HVACAction.HEATING),
        ("33", "0", "0", HVACAction.IDLE),
        ("1", "0", "100", HVACAction.COOLING),
        ("1", "0", "0", HVACAction.IDLE),
        ("33", "10", "100", HVACAction.HEATING),
        ("1", "100", "10", HVACAction.COOLING),
    ],
)
async def test_rtc_hvac_action(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    state_indication: str | None,
    heating: str,
    cooling: str,
    expected: HVACAction,
) -> None:
    """Test a controller's action follows its state indication and values."""
    await setup_with_channels(
        hass,
        mock_config_entry,
        mock_free_at_home_settings,
        [
            _build_rtc(
                build_device(SERIAL),
                outputs={
                    Pairing.AL_STATE_INDICATION: state_indication,
                    Pairing.AL_ACTUATING_VALUE_HEATING: heating,
                    Pairing.AL_ACTUATING_VALUE_COOLING: cooling,
                },
            )
        ],
    )

    state = hass.states.get(_entity_id(entity_registry, RTC))
    assert state.state == HVACMode.HEAT_COOL
    assert state.attributes[ATTR_HVAC_ACTION] == expected


@pytest.mark.parametrize(
    ("heating_active", "demand", "expected"),
    [
        ("0", "0", HVACAction.IDLE),
        ("1", "0", HVACAction.HEATING),
        # Some thermostats report a demand without the active flag.
        ("0", "30", HVACAction.HEATING),
    ],
)
async def test_radiator_hvac_action(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    heating_active: str,
    demand: str,
    expected: HVACAction,
) -> None:
    """Test a radiator thermostat's action follows its heating state."""
    await setup_with_channels(
        hass,
        mock_config_entry,
        mock_free_at_home_settings,
        [
            _build_radiator(
                build_device(SERIAL),
                outputs={
                    Pairing.AL_HEATING_ACTIVE: heating_active,
                    Pairing.AL_HEATING_DEMAND: demand,
                },
            )
        ],
    )

    state = hass.states.get(_entity_id(entity_registry, RADIATOR))
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_HVAC_ACTION] == expected


@pytest.mark.parametrize(
    "build", [_build_rtc, _build_radiator], ids=["controller", "radiator"]
)
async def test_climate_off(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    build: Callable[..., RoomTemperatureController],
) -> None:
    """Test a switched off climate entity has no action and no target."""
    channel = build(
        build_device(SERIAL),
        outputs={
            Pairing.AL_CONTROLLER_ON_OFF: "0",
            Pairing.AL_STATE_INDICATION: "36",
        },
    )
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )

    state = hass.states.get(_entity_id(entity_registry, channel.channel_id))
    assert state.state == HVACMode.OFF
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.OFF
    assert state.attributes[ATTR_TEMPERATURE] is None
    assert state.attributes[ATTR_CURRENT_TEMPERATURE] == channel.current_temperature
    assert state.attributes[ATTR_PRESET_MODE] == "eco"


# Each report from the default state, with the state and the attributes it
# changes. The library reads unreadable temperatures as unknown and an
# unreadable actuating value or demand as 0.
RTC_REPORTS = [
    (
        Pairing.AL_CONTROLLER_ON_OFF,
        "0",
        HVACMode.OFF,
        {ATTR_HVAC_ACTION: HVACAction.OFF, ATTR_TEMPERATURE: None},
    ),
    (Pairing.AL_SET_POINT_TEMPERATURE, "23.5", None, {ATTR_TEMPERATURE: 23.5}),
    (Pairing.AL_SET_POINT_TEMPERATURE, "", None, {ATTR_TEMPERATURE: None}),
    (Pairing.AL_MEASURED_TEMPERATURE, "19.8", None, {ATTR_CURRENT_TEMPERATURE: 19.8}),
    (Pairing.AL_MEASURED_TEMPERATURE, "", None, {ATTR_CURRENT_TEMPERATURE: None}),
    (
        Pairing.AL_ACTUATING_VALUE_HEATING,
        "40",
        None,
        {"heating": 40, ATTR_HVAC_ACTION: HVACAction.HEATING},
    ),
    # In heating mode, a cooling value is not carried out.
    (Pairing.AL_ACTUATING_VALUE_COOLING, "60", None, {"cooling": 60}),
    (Pairing.AL_STATE_INDICATION, "37", None, {ATTR_PRESET_MODE: "eco"}),
]
RADIATOR_REPORTS = [
    (
        Pairing.AL_CONTROLLER_ON_OFF,
        "0",
        HVACMode.OFF,
        {ATTR_HVAC_ACTION: HVACAction.OFF, ATTR_TEMPERATURE: None},
    ),
    (Pairing.AL_SET_POINT_TEMPERATURE, "23.5", None, {ATTR_TEMPERATURE: 23.5}),
    (Pairing.AL_MEASURED_TEMPERATURE, "19.8", None, {ATTR_CURRENT_TEMPERATURE: 19.8}),
    (
        Pairing.AL_HEATING_ACTIVE,
        "1",
        None,
        {"heating_active": True, ATTR_HVAC_ACTION: HVACAction.HEATING},
    ),
    (
        Pairing.AL_HEATING_DEMAND,
        "55",
        None,
        {"heating": 55, "heating_active": True, ATTR_HVAC_ACTION: HVACAction.HEATING},
    ),
    (Pairing.AL_STATE_INDICATION, "37", None, {ATTR_PRESET_MODE: "eco"}),
]


@pytest.mark.parametrize(
    ("build", "pairing", "value", "expected_state", "changes"),
    [
        *((_build_rtc, *report) for report in RTC_REPORTS),
        *((_build_radiator, *report) for report in RADIATOR_REPORTS),
    ],
    ids=[
        *(f"controller-{pairing.name}-{value!r}" for pairing, value, *_ in RTC_REPORTS),
        *(
            f"radiator-{pairing.name}-{value!r}"
            for pairing, value, *_ in RADIATOR_REPORTS
        ),
    ],
)
async def test_climate_follows_sysap(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    build: Callable[..., RoomTemperatureController],
    pairing: Pairing,
    value: str,
    expected_state: HVACMode | None,
    changes: dict[str, Any],
) -> None:
    """Test a climate entity shows what the SysAP reports without a command."""
    device = build_device(SERIAL)
    channel = build(device)
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, channel.channel_id)
    before = hass.states.get(entity_id)

    _report(channel, pairing, value)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == (expected_state or before.state)
    assert state.attributes == {**before.attributes, **changes}
    device.api.set_datapoint.assert_not_awaited()


async def test_rtc_hvac_action_follows_state_indication(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test a reported state indication alone changes a controller's action."""
    channel = _build_rtc(
        build_device(SERIAL),
        outputs={
            Pairing.AL_STATE_INDICATION: "65",
            Pairing.AL_ACTUATING_VALUE_HEATING: "20",
            Pairing.AL_ACTUATING_VALUE_COOLING: "100",
        },
    )
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, RTC)
    assert hass.states.get(entity_id).attributes[ATTR_HVAC_ACTION] == HVACAction.IDLE

    for state_indication, expected in (
        ("33", HVACAction.HEATING),
        ("1", HVACAction.COOLING),
        ("97", HVACAction.IDLE),
    ):
        _report(channel, Pairing.AL_STATE_INDICATION, state_indication)
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).attributes[ATTR_HVAC_ACTION] == expected


async def test_radiator_hvac_action_follows_demand(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test a radiator thermostat heats while it reports a demand."""
    channel = _build_radiator(build_device(SERIAL))
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, RADIATOR)

    # The library reads an unreadable demand as 0.
    for demand, heating, expected in (
        ("55", 55, HVACAction.HEATING),
        ("70", 70, HVACAction.HEATING),
        ("", 0, HVACAction.IDLE),
    ):
        _report(channel, Pairing.AL_HEATING_DEMAND, demand)
        await hass.async_block_till_done()
        attributes = hass.states.get(entity_id).attributes
        assert attributes["heating"] == heating
        assert attributes[ATTR_HVAC_ACTION] == expected


@pytest.mark.parametrize(
    ("build", "on_mode"),
    [(_build_rtc, HVACMode.HEAT_COOL), (_build_radiator, HVACMode.HEAT)],
    ids=["controller", "radiator"],
)
async def test_climate_switch_on_and_off(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    build: Callable[..., RoomTemperatureController],
    on_mode: HVACMode,
) -> None:
    """Test the HVAC modes and turning on and off switch the channel."""
    device = build_device(SERIAL)
    channel = build(device)
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, channel.channel_id)

    for mode in (on_mode, HVACMode.OFF):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_HVAC_MODE,
            {ATTR_ENTITY_ID: entity_id, ATTR_HVAC_MODE: mode},
            blocking=True,
        )
    for service in (SERVICE_TURN_ON, SERVICE_TURN_OFF):
        await hass.services.async_call(
            CLIMATE_DOMAIN, service, {ATTR_ENTITY_ID: entity_id}, blocking=True
        )

    switch_on = _set_datapoint(channel.channel_id, "idp0000", "1")
    switch_off = _set_datapoint(channel.channel_id, "idp0000", "0")
    assert device.api.set_datapoint.await_args_list == [
        switch_on,
        switch_off,
        switch_on,
        switch_off,
    ]


@pytest.mark.parametrize(
    ("build", "unsupported_mode"),
    [(_build_rtc, HVACMode.HEAT), (_build_radiator, HVACMode.HEAT_COOL)],
    ids=["controller", "radiator"],
)
async def test_climate_rejects_unsupported_hvac_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    build: Callable[..., RoomTemperatureController],
    unsupported_mode: HVACMode,
) -> None:
    """Test a controller only heats and cools, and a radiator only heats."""
    device = build_device(SERIAL)
    channel = build(device)
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_HVAC_MODE,
            {
                ATTR_ENTITY_ID: _entity_id(entity_registry, channel.channel_id),
                ATTR_HVAC_MODE: unsupported_mode,
            },
            blocking=True,
        )
    device.api.set_datapoint.assert_not_awaited()


@pytest.mark.parametrize(
    "build", [_build_rtc, _build_radiator], ids=["controller", "radiator"]
)
async def test_climate_preset_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    build: Callable[..., RoomTemperatureController],
) -> None:
    """Test the eco preset switches the channel's eco mode."""
    device = build_device(SERIAL)
    channel = build(device)
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, channel.channel_id)

    for preset_mode in ("eco", "none"):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: entity_id, ATTR_PRESET_MODE: preset_mode},
            blocking=True,
        )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: entity_id, ATTR_PRESET_MODE: "away"},
            blocking=True,
        )

    assert device.api.set_datapoint.await_args_list == [
        _set_datapoint(channel.channel_id, "idp0001", "1"),
        _set_datapoint(channel.channel_id, "idp0001", "0"),
    ]


@pytest.mark.parametrize(
    "build", [_build_rtc, _build_radiator], ids=["controller", "radiator"]
)
async def test_climate_set_temperature(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    build: Callable[..., RoomTemperatureController],
) -> None:
    """Test setting a target temperature from 7 to 35 °C."""
    device = build_device(SERIAL)
    channel = build(device)
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, channel.channel_id)

    for temperature in (7, 22.5, 35):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: temperature},
            blocking=True,
        )
    for temperature in (6.5, 35.5):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                CLIMATE_DOMAIN,
                SERVICE_SET_TEMPERATURE,
                {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: temperature},
                blocking=True,
            )

    # The library clamps to the same range and sends its lower bound as 7.
    assert device.api.set_datapoint.await_args_list == [
        _set_datapoint(channel.channel_id, "idp0002", value)
        for value in ("7", "22.5", "35.0")
    ]


@pytest.mark.parametrize(
    ("unit_system", "current_temperature", "target_temperature", "set_temperature"),
    [(METRIC_SYSTEM, 21.3, 21.5, 22.5), (US_CUSTOMARY_SYSTEM, 70, 71, 72.5)],
    ids=["metric", "us_customary"],
)
async def test_climate_temperature_unit_conversion(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    unit_system: UnitSystem,
    current_temperature: float,
    target_temperature: float,
    set_temperature: float,
) -> None:
    """Test Home Assistant converts temperatures from and to Celsius."""
    hass.config.units = unit_system
    device = build_device(SERIAL)
    await setup_with_channels(
        hass,
        mock_config_entry,
        mock_free_at_home_settings,
        [_build_rtc(device, outputs={Pairing.AL_SET_POINT_TEMPERATURE: "21.5"})],
    )
    entity_id = _entity_id(entity_registry, RTC)

    attributes = hass.states.get(entity_id).attributes
    assert attributes[ATTR_CURRENT_TEMPERATURE] == current_temperature
    assert attributes[ATTR_TEMPERATURE] == target_temperature

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: set_temperature},
        blocking=True,
    )
    device.api.set_datapoint.assert_awaited_once_with(
        device_serial=SERIAL, channel_id=RTC, datapoint="idp0002", value="22.5"
    )


async def test_climate_update_entity(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test updating a climate entity refreshes its state from the SysAP."""
    assert await async_setup_component(hass, HOMEASSISTANT_DOMAIN, {})
    device = build_device(SERIAL)
    channel = _build_rtc(device)
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, RTC)
    values = {
        channel.get_output_by_pairing(pairing)[0]: value
        for pairing, value in {
            Pairing.AL_CONTROLLER_ON_OFF: "1",
            Pairing.AL_SET_POINT_TEMPERATURE: "23",
            Pairing.AL_MEASURED_TEMPERATURE: "22.4",
            Pairing.AL_STATE_INDICATION: "1",
            Pairing.AL_ACTUATING_VALUE_HEATING: "0",
            Pairing.AL_ACTUATING_VALUE_COOLING: "60",
        }.items()
    }
    device.api.get_datapoint.side_effect = lambda **kwargs: [
        values[kwargs["datapoint"]]
    ]

    await hass.services.async_call(
        HOMEASSISTANT_DOMAIN,
        SERVICE_UPDATE_ENTITY,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    attributes = hass.states.get(entity_id).attributes
    assert attributes[ATTR_TEMPERATURE] == 23
    assert attributes[ATTR_CURRENT_TEMPERATURE] == 22.4
    assert attributes["cooling"] == 60
    assert attributes[ATTR_HVAC_ACTION] == HVACAction.COOLING
    assert sorted(
        call.kwargs["datapoint"] for call in device.api.get_datapoint.await_args_list
    ) == sorted(values)


async def test_climate_removes_callbacks_on_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test unloaded climate entities no longer follow their channels."""
    device = build_device(SERIAL)
    rtc = _build_rtc(device)
    radiator = _build_radiator(device)
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [rtc, radiator]
    )
    entity_ids = [
        _entity_id(entity_registry, channel_id) for channel_id in (RTC, RADIATOR)
    ]

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    states = [hass.states.get(entity_id) for entity_id in entity_ids]

    for channel in (rtc, radiator):
        _report(channel, Pairing.AL_CONTROLLER_ON_OFF, "0")
    await hass.async_block_till_done()
    assert [hass.states.get(entity_id) for entity_id in entity_ids] == states
    common = ["state", "current_temperature", "heating", "cooling"]
    common += ["target_temperature", "eco_mode"]
    assert rtc._callbacks == dict.fromkeys(
        [*common, "heating_mode", "heating_cooling_active"], set()
    )
    assert radiator._callbacks == dict.fromkeys([*common, "heating_active"], set())


@pytest.mark.parametrize(
    ("create_subdevices", "multi_device_identifier"),
    [
        (False, (DOMAIN, SERIAL)),
        (True, (DOMAIN, f"{SERIAL}_{RTC}")),
    ],
)
async def test_climate_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    create_subdevices: bool,
    multi_device_identifier: tuple[str, str],
) -> None:
    """Test a climate entity of a multi-channel device belongs to a subdevice."""
    entry = MockConfigEntry(
        version=mock_config_entry.version,
        minor_version=mock_config_entry.minor_version,
        domain=DOMAIN,
        title=mock_config_entry.title,
        data={**mock_config_entry.data, CONF_CREATE_SUBDEVICES: create_subdevices},
        source=mock_config_entry.source,
        unique_id=mock_config_entry.unique_id,
    )
    # A device without a room and with several channels is a multi-device.
    multi_device = build_device(SERIAL)
    multi_channel = _build_rtc(multi_device)
    _build_rtc(multi_device, "ch0001")
    assert multi_device.is_multi_device
    single_device = build_device("ABB700000002")
    single_channel = _build_radiator(single_device, RTC)
    assert not single_device.is_multi_device

    await setup_with_channels(
        hass, entry, mock_free_at_home_settings, [multi_channel, single_channel]
    )

    def device_identifiers(unique_id: str) -> set[tuple[str, str]]:
        """Return the identifiers of the device of a climate entity."""
        entity_id = entity_registry.async_get_entity_id(
            CLIMATE_DOMAIN, DOMAIN, unique_id
        )
        entity_entry = entity_registry.async_get(entity_id)
        return device_registry.async_get(entity_entry.device_id).identifiers

    assert device_identifiers(f"{SERIAL}_{RTC}_climate") == {multi_device_identifier}
    assert device_identifiers(f"ABB700000002_{RTC}_climate") == {
        (DOMAIN, "ABB700000002")
    }


# compat: homeassistant<2026.11 - native_* temperature properties replaced the legacy names
@pytest.mark.parametrize("native_api", [False, True])
def test_temperature_api_compatibility(
    monkeypatch: pytest.MonkeyPatch, native_api: bool
) -> None:
    """Expose legacy aliases only when HA lacks the native temperature API.

    Each Home Assistant release takes only one branch, so the module is run
    again with and without the native API, and the entity is built directly.
    """
    properties = ("temperature_unit", "current_temperature", "target_temperature")
    for name in properties:
        if native_api:
            monkeypatch.setattr(
                ClimateEntity,
                f"native_{name}",
                property(lambda self: None),
                raising=False,
            )
        else:
            monkeypatch.delattr(ClimateEntity, f"native_{name}", raising=False)

    platform = run_path(climate_platform.__file__, run_name=climate_platform.__name__)
    base_class = platform["FreeAtHomeClimateEntity"]
    channel = _build_rtc(build_device(SERIAL))
    entity = base_class(
        channel, sysap_serial_number="TEST123456", create_subdevices=False
    )

    for name in properties:
        assert (name in base_class.__dict__) is not native_api
    if native_api:
        return
    assert entity.temperature_unit == UnitOfTemperature.CELSIUS
    assert entity.current_temperature == 21.3
    assert entity.target_temperature == 21.0

    _report(channel, Pairing.AL_CONTROLLER_ON_OFF, "0")
    assert entity.target_temperature is None


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
