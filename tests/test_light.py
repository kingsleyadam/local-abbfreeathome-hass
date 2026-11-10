"""Test ABB-free@home light."""

from collections.abc import Callable, Mapping
from typing import Any
from unittest.mock import MagicMock, call

from abbfreeathome.bin.pairing import Pairing
from abbfreeathome.bin.parameter import Parameter
from abbfreeathome.channels.base import Base
from abbfreeathome.channels.dimming_actuator import (
    ColorTemperatureActuator,
    DimmingActuator,
)
from abbfreeathome.channels.virtual.virtual_dimming_actuator import (
    VirtualDimmingActuator,
)
from abbfreeathome.device import Device
import pytest
from syrupy.assertion import SnapshotAssertion

from custom_components.abbfreeathome_ci.const import CONF_CREATE_SUBDEVICES, DOMAIN
from custom_components.abbfreeathome_ci.light import FreeAtHomeLightEntity
from homeassistant.components.homeassistant import (
    DOMAIN as HOMEASSISTANT_DOMAIN,
    SERVICE_UPDATE_ENTITY,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP_KELVIN,
    DOMAIN as LIGHT_DOMAIN,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

from .common import (
    MockConfigEntry,
    build_channel,
    build_device,
    setup_with_channels,
    snapshot_entities,
)

SERIAL = "ABB700000001"
DIMMER = "ch0000"
COLOR = "ch0001"
VIRTUAL = "ch0002"

WARMEST = Parameter.PID_TEMPERATURE_COLOR_PHYSICAL_WARMEST
COOLEST = Parameter.PID_TEMPERATURE_COLOR_PHYSICAL_COOLEST


@pytest.fixture(autouse=True)
def light_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load only the light platform."""
    monkeypatch.setattr(
        "custom_components.abbfreeathome_ci.PLATFORMS", [Platform.LIGHT]
    )


def _outputs(
    defaults: Mapping[Pairing, str], overrides: Mapping[Pairing, str | None]
) -> dict[Pairing, str]:
    """Return outputs with overridden values; None leaves an output out."""
    outputs = {**defaults, **overrides}
    return {pairing: value for pairing, value in outputs.items() if value is not None}


def _build_dimmer(
    device: Device,
    channel_id: str = DIMMER,
    outputs: Mapping[Pairing, str | None] | None = None,
) -> DimmingActuator:
    """Build a real dimming actuator, on at 50 %.

    It is switched on the AL_SWITCH_ON_OFF input (idp0000) and dimmed on the
    AL_ABSOLUTE_SET_VALUE_CONTROL input (idp0001).
    """
    return build_channel(
        DimmingActuator,
        device,
        channel_id,
        inputs={
            Pairing.AL_SWITCH_ON_OFF: "0",
            Pairing.AL_ABSOLUTE_SET_VALUE_CONTROL: "0",
        },
        outputs=_outputs(
            {
                Pairing.AL_INFO_ON_OFF: "1",
                Pairing.AL_INFO_ACTUAL_DIMMING_VALUE: "50",
                Pairing.AL_INFO_FORCE: "0",
            },
            outputs or {},
        ),
    )


def _build_color_light(
    device: Device,
    channel_id: str = COLOR,
    outputs: Mapping[Pairing, str | None] | None = None,
    parameters: Mapping[Parameter, str | None] | None = None,
) -> ColorTemperatureActuator:
    """Build a real color temperature actuator, on at 80 % and 4600 K.

    Like a dimmer, plus the color temperature from 0 (warmest, 2700 K) to
    100 (coolest, 6500 K) on the AL_COLOR_TEMPERATURE input (idp0002).
    """
    return build_channel(
        ColorTemperatureActuator,
        device,
        channel_id,
        inputs={
            Pairing.AL_SWITCH_ON_OFF: "0",
            Pairing.AL_ABSOLUTE_SET_VALUE_CONTROL: "0",
            Pairing.AL_COLOR_TEMPERATURE: "0",
        },
        outputs=_outputs(
            {
                Pairing.AL_INFO_ON_OFF: "1",
                Pairing.AL_INFO_ACTUAL_DIMMING_VALUE: "80",
                Pairing.AL_INFO_FORCE: "0",
                Pairing.AL_INFO_COLOR_TEMPERATURE: "50",
            },
            outputs or {},
        ),
        parameters={WARMEST: "2700", COOLEST: "6500", **(parameters or {})},
    )


def _build_virtual_dimmer(
    device: Device,
    channel_id: str = VIRTUAL,
    outputs: Mapping[Pairing, str | None] | None = None,
) -> VirtualDimmingActuator:
    """Build a real virtual dimming actuator, on at 25 %.

    Home Assistant acts as the dimmer: it publishes the switching state on
    the AL_INFO_ON_OFF output (odp0000) and the brightness on the
    AL_INFO_ACTUAL_DIMMING_VALUE output (odp0001). The inputs carry requests
    from the SysAP, which the event platform handles.
    """
    return build_channel(
        VirtualDimmingActuator,
        device,
        channel_id,
        inputs={
            Pairing.AL_SWITCH_ON_OFF: "0",
            Pairing.AL_RELATIVE_SET_VALUE_CONTROL: "0",
            Pairing.AL_ABSOLUTE_SET_VALUE_CONTROL: "0",
        },
        outputs=_outputs(
            {
                Pairing.AL_INFO_ON_OFF: "1",
                Pairing.AL_INFO_ACTUAL_DIMMING_VALUE: "25",
            },
            outputs or {},
        ),
    )


BUILDERS = [_build_dimmer, _build_color_light, _build_virtual_dimmer]
BUILDER_IDS = ["dimmer", "color", "virtual"]


def _report(channel: Base, pairing: Pairing, value: str) -> None:
    """Report the value of the channel's output with the pairing, as the SysAP."""
    datapoint, _ = channel.get_output_by_pairing(pairing)
    channel.update_channel(
        f"{channel.device_serial}/{channel.channel_id}/{datapoint}", value
    )


def _entity_id(entity_registry: er.EntityRegistry, channel_id: str) -> str:
    """Return the entity ID of the light of a channel by its unique ID."""
    entity_id = entity_registry.async_get_entity_id(
        LIGHT_DOMAIN, DOMAIN, f"{SERIAL}_{channel_id}_light"
    )
    assert entity_id is not None
    return entity_id


def _set_datapoint(channel_id: str, datapoint: str, value: str) -> Any:
    """Return the expected call to set a datapoint of a channel."""
    return call(
        device_serial=SERIAL, channel_id=channel_id, datapoint=datapoint, value=value
    )


async def test_light_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the lights of a dimmer, a color temperature and a virtual dimmer."""
    device = build_device(SERIAL)
    await setup_with_channels(
        hass,
        mock_config_entry,
        mock_free_at_home_settings,
        [build(device) for build in BUILDERS],
    )

    snapshot_entities(hass, snapshot, mock_config_entry.entry_id)


@pytest.mark.parametrize(
    ("build", "outputs", "parameters", "expected_state", "expected"),
    [
        (
            _build_dimmer,
            {Pairing.AL_INFO_ACTUAL_DIMMING_VALUE: None},
            None,
            STATE_ON,
            {ATTR_BRIGHTNESS: None},
        ),
        (
            _build_color_light,
            {Pairing.AL_INFO_COLOR_TEMPERATURE: None},
            None,
            STATE_ON,
            {ATTR_BRIGHTNESS: 204, ATTR_COLOR_TEMP_KELVIN: None},
        ),
        (
            _build_color_light,
            None,
            {WARMEST: None},
            STATE_ON,
            {ATTR_BRIGHTNESS: 204, ATTR_COLOR_TEMP_KELVIN: None},
        ),
        (
            _build_color_light,
            None,
            {COOLEST: None},
            STATE_ON,
            {ATTR_BRIGHTNESS: 204, ATTR_COLOR_TEMP_KELVIN: None},
        ),
        (
            _build_virtual_dimmer,
            {Pairing.AL_INFO_ON_OFF: None},
            None,
            STATE_UNKNOWN,
            {},
        ),
    ],
    ids=[
        "dimmer-no-brightness",
        "color-no-color-temperature",
        "color-no-warmest",
        "color-no-coolest",
        "virtual-no-state",
    ],
)
async def test_light_without_values(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    build: Callable[..., Base],
    outputs: dict[Pairing, str | None] | None,
    parameters: dict[Parameter, str | None] | None,
    expected_state: str,
    expected: dict[str, Any],
) -> None:
    """Test a light without a reported value or color temperature bounds."""
    kwargs = {"outputs": outputs}
    if parameters is not None:
        kwargs["parameters"] = parameters
    channel = build(build_device(SERIAL), **kwargs)
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )

    state = hass.states.get(_entity_id(entity_registry, channel.channel_id))
    assert state.state == expected_state
    assert {key: state.attributes.get(key) for key in expected} == expected


# Each report from the default state, with the state and attributes it sets.
DIMMER_REPORTS = [
    (Pairing.AL_INFO_ON_OFF, "0", STATE_OFF, {ATTR_BRIGHTNESS: None}),
    (Pairing.AL_INFO_ACTUAL_DIMMING_VALUE, "100", STATE_ON, {ATTR_BRIGHTNESS: 255}),
    (Pairing.AL_INFO_ACTUAL_DIMMING_VALUE, "1", STATE_ON, {ATTR_BRIGHTNESS: 3}),
    (Pairing.AL_INFO_ACTUAL_DIMMING_VALUE, "0", STATE_ON, {ATTR_BRIGHTNESS: 0}),
]
COLOR_REPORTS = [
    (
        Pairing.AL_INFO_ON_OFF,
        "0",
        STATE_OFF,
        {ATTR_BRIGHTNESS: None, ATTR_COLOR_MODE: None, ATTR_COLOR_TEMP_KELVIN: None},
    ),
    (Pairing.AL_INFO_ACTUAL_DIMMING_VALUE, "50", STATE_ON, {ATTR_BRIGHTNESS: 128}),
    (Pairing.AL_INFO_COLOR_TEMPERATURE, "0", STATE_ON, {ATTR_COLOR_TEMP_KELVIN: 2700}),
    (
        Pairing.AL_INFO_COLOR_TEMPERATURE,
        "100",
        STATE_ON,
        {ATTR_COLOR_TEMP_KELVIN: 6500},
    ),
]
VIRTUAL_REPORTS = [
    (Pairing.AL_INFO_ON_OFF, "0", STATE_OFF, {ATTR_BRIGHTNESS: None}),
    (Pairing.AL_INFO_ON_OFF, "", STATE_UNKNOWN, {}),
    (Pairing.AL_INFO_ACTUAL_DIMMING_VALUE, "80", STATE_ON, {ATTR_BRIGHTNESS: 204}),
]


@pytest.mark.parametrize(
    ("build", "pairing", "value", "expected_state", "expected"),
    [
        *((_build_dimmer, *report) for report in DIMMER_REPORTS),
        *((_build_color_light, *report) for report in COLOR_REPORTS),
        *((_build_virtual_dimmer, *report) for report in VIRTUAL_REPORTS),
    ],
    ids=[
        f"{kind}-{pairing.name}-{value!r}"
        for kind, reports in (
            ("dimmer", DIMMER_REPORTS),
            ("color", COLOR_REPORTS),
            ("virtual", VIRTUAL_REPORTS),
        )
        for pairing, value, *_ in reports
    ],
)
async def test_light_follows_sysap(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    build: Callable[..., Base],
    pairing: Pairing,
    value: str,
    expected_state: str,
    expected: dict[str, Any],
) -> None:
    """Test a light shows what the SysAP reports without a command."""
    device = build_device(SERIAL)
    channel = build(device)
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, channel.channel_id)

    _report(channel, pairing, value)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == expected_state
    assert {key: state.attributes.get(key) for key in expected} == expected
    device.api.set_datapoint.assert_not_awaited()


@pytest.mark.parametrize(
    ("build", "service", "data", "datapoint", "value"),
    [
        (_build_dimmer, SERVICE_TURN_ON, {}, "idp0000", "1"),
        (_build_dimmer, SERVICE_TURN_OFF, {}, "idp0000", "0"),
        (_build_dimmer, SERVICE_TURN_ON, {ATTR_BRIGHTNESS: 128}, "idp0001", "50"),
        (_build_dimmer, SERVICE_TURN_ON, {ATTR_BRIGHTNESS_PCT: 100}, "idp0001", "100"),
        # The library raises the lowest brightness to 1 %.
        (_build_dimmer, SERVICE_TURN_ON, {ATTR_BRIGHTNESS: 1}, "idp0001", "1"),
        # Home Assistant turns a light off for brightness 0.
        (_build_dimmer, SERVICE_TURN_ON, {ATTR_BRIGHTNESS: 0}, "idp0000", "0"),
        # Home Assistant drops a color temperature a light does not support.
        (
            _build_dimmer,
            SERVICE_TURN_ON,
            {ATTR_COLOR_TEMP_KELVIN: 4600},
            "idp0000",
            "1",
        ),
        (_build_color_light, SERVICE_TURN_ON, {}, "idp0000", "1"),
        (_build_color_light, SERVICE_TURN_OFF, {}, "idp0000", "0"),
        (_build_color_light, SERVICE_TURN_ON, {ATTR_BRIGHTNESS: 64}, "idp0001", "25"),
        (
            _build_color_light,
            SERVICE_TURN_ON,
            {ATTR_COLOR_TEMP_KELVIN: 3650},
            "idp0002",
            "25.0",
        ),
    ],
    ids=[
        "dimmer-on",
        "dimmer-off",
        "dimmer-brightness",
        "dimmer-brightness-pct",
        "dimmer-lowest-brightness",
        "dimmer-brightness-zero",
        "dimmer-color-temperature",
        "color-on",
        "color-off",
        "color-brightness",
        "color-color-temperature",
    ],
)
async def test_light_command(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    build: Callable[..., Base],
    service: str,
    data: dict[str, Any],
    datapoint: str,
    value: str,
) -> None:
    """Test a light command sets one input of the actuator on the SysAP."""
    device = build_device(SERIAL)
    channel = build(device)
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )

    await hass.services.async_call(
        LIGHT_DOMAIN,
        service,
        {ATTR_ENTITY_ID: _entity_id(entity_registry, channel.channel_id), **data},
        blocking=True,
    )

    assert device.api.set_datapoint.await_args_list == [
        _set_datapoint(channel.channel_id, datapoint, value)
    ]


@pytest.mark.parametrize("missing", [WARMEST, COOLEST])
async def test_color_light_without_bounds_turns_on(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    missing: Parameter,
) -> None:
    """Test a color temperature without known bounds only turns the light on."""
    device = build_device(SERIAL)
    await setup_with_channels(
        hass,
        mock_config_entry,
        mock_free_at_home_settings,
        [_build_color_light(device, parameters={missing: None})],
    )

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: _entity_id(entity_registry, COLOR),
            ATTR_COLOR_TEMP_KELVIN: 4600,
        },
        blocking=True,
    )

    assert device.api.set_datapoint.await_args_list == [
        _set_datapoint(COLOR, "idp0000", "1")
    ]


@pytest.mark.parametrize(
    ("service", "data", "calls", "expected_state", "expected_brightness"),
    [
        (SERVICE_TURN_ON, {}, [("odp0000", "1")], STATE_ON, 64),
        (SERVICE_TURN_OFF, {}, [("odp0000", "0")], STATE_OFF, None),
        (
            SERVICE_TURN_ON,
            {ATTR_BRIGHTNESS: 128},
            [("odp0001", "50"), ("odp0000", "1")],
            STATE_ON,
            128,
        ),
    ],
    ids=["on", "off", "brightness"],
)
async def test_virtual_light_publishes_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    service: str,
    data: dict[str, Any],
    calls: list[tuple[str, str]],
    expected_state: str,
    expected_brightness: int | None,
) -> None:
    """Test a virtual dimmer publishes its state and shows it at once.

    The SysAP does not echo the outputs of a virtual device, so the light
    shows what it published. A brightness also switches it on.
    """
    device = build_device(SERIAL)
    channel = _build_virtual_dimmer(
        device,
        outputs={Pairing.AL_INFO_ON_OFF: "1" if service == SERVICE_TURN_OFF else "0"},
    )
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, VIRTUAL)

    await hass.services.async_call(
        LIGHT_DOMAIN, service, {ATTR_ENTITY_ID: entity_id, **data}, blocking=True
    )

    assert device.api.set_datapoint.await_args_list == [
        _set_datapoint(VIRTUAL, datapoint, value) for datapoint, value in calls
    ]
    state = hass.states.get(entity_id)
    assert state.state == expected_state
    assert state.attributes.get(ATTR_BRIGHTNESS) == expected_brightness


async def test_color_temperature_on_light_without_it() -> None:
    """Test a light without the color temperature mode ignores one.

    Home Assistant neither reads the color temperature of such a light nor
    passes one to it, so the light is built directly to reach these
    branches.
    """
    device = build_device(SERIAL)
    entity = FreeAtHomeLightEntity(
        _build_dimmer(device),
        sysap_serial_number="TEST123456",
        create_subdevices=False,
    )

    assert entity.color_temp_kelvin is None
    await entity.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: 4600})

    device.api.set_datapoint.assert_not_awaited()


async def test_light_update_entity(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test updating a light refreshes its state from the SysAP."""
    assert await async_setup_component(hass, HOMEASSISTANT_DOMAIN, {})
    device = build_device(SERIAL)
    channel = _build_color_light(device)
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [channel]
    )
    entity_id = _entity_id(entity_registry, COLOR)
    values = {
        channel.get_output_by_pairing(pairing)[0]: value
        for pairing, value in {
            Pairing.AL_INFO_ON_OFF: "1",
            Pairing.AL_INFO_ACTUAL_DIMMING_VALUE: "25",
            Pairing.AL_INFO_FORCE: "0",
            Pairing.AL_INFO_COLOR_TEMPERATURE: "0",
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
    assert attributes[ATTR_BRIGHTNESS] == 64
    assert attributes[ATTR_COLOR_TEMP_KELVIN] == 2700
    assert sorted(
        call.kwargs["datapoint"] for call in device.api.get_datapoint.await_args_list
    ) == sorted(values)


async def test_light_removes_callbacks_on_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test unloaded lights no longer follow their channels."""
    device = build_device(SERIAL)
    dimmer, color, virtual = (build(device) for build in BUILDERS)
    await setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [dimmer, color, virtual]
    )
    entity_ids = [
        _entity_id(entity_registry, channel_id)
        for channel_id in (DIMMER, COLOR, VIRTUAL)
    ]

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    states = [hass.states.get(entity_id) for entity_id in entity_ids]

    for channel in (dimmer, color, virtual):
        _report(channel, Pairing.AL_INFO_ON_OFF, "0")
    await hass.async_block_till_done()
    assert [hass.states.get(entity_id) for entity_id in entity_ids] == states
    assert dimmer._callbacks == {"state": set(), "brightness": set()}
    assert color._callbacks == dict.fromkeys(
        ["state", "brightness", "color_temperature"], set()
    )
    # The virtual dimmer starts with empty callbacks for all its attributes.
    assert not any(virtual._callbacks.values())


@pytest.mark.parametrize(
    ("create_subdevices", "multi_device_identifier"),
    [
        (False, (DOMAIN, SERIAL)),
        (True, (DOMAIN, f"{SERIAL}_{DIMMER}")),
    ],
)
async def test_light_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_free_at_home_settings: MagicMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    create_subdevices: bool,
    multi_device_identifier: tuple[str, str],
) -> None:
    """Test a light of a multi-channel device belongs to a subdevice if enabled."""
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
    multi_channel = _build_dimmer(multi_device)
    _build_dimmer(multi_device, "ch0001")
    assert multi_device.is_multi_device
    single_device = build_device("ABB700000002")
    single_channel = _build_dimmer(single_device)
    assert not single_device.is_multi_device

    await setup_with_channels(
        hass, entry, mock_free_at_home_settings, [multi_channel, single_channel]
    )

    def device_identifiers(unique_id: str) -> set[tuple[str, str]]:
        """Return the identifiers of the device of a light."""
        entity_id = entity_registry.async_get_entity_id(LIGHT_DOMAIN, DOMAIN, unique_id)
        entity_entry = entity_registry.async_get(entity_id)
        return device_registry.async_get(entity_entry.device_id).identifiers

    assert device_identifiers(f"{SERIAL}_{DIMMER}_light") == {multi_device_identifier}
    assert device_identifiers(f"ABB700000002_{DIMMER}_light") == {
        (DOMAIN, "ABB700000002")
    }
