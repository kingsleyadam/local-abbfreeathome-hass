"""Test the ABB-free@home integration initialization."""

import asyncio
import inspect
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from abbfreeathome import DevicesChangedEvent
from abbfreeathome.bin.interface import Interface
from abbfreeathome.channels.trigger import Trigger
from abbfreeathome.device import Device
from abbfreeathome.exceptions import (
    BadRequestException,
    ClientConnectionError,
    ConnectionTimeoutException,
    ForbiddenAuthException,
    InvalidApiResponseException,
    InvalidCredentialsException,
    InvalidHostException,
    SslErrorException,
)
from abbfreeathome.floorplan import Floorplan
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.abbfreeathome_ci import (
    async_migrate_entry,
    async_remove_config_entry_device,
    async_setup,
    async_setup_entry,
    async_setup_service,
    async_unload_entry,
)
from custom_components.abbfreeathome_ci.const import (
    CONF_CREATE_SUBDEVICES,
    CONF_CREATE_UNRESPONSIVE_REPAIRS,
    CONF_INCLUDE_ORPHAN_CHANNELS,
    CONF_INCLUDE_VIRTUAL_DEVICES,
    CONF_SERIAL,
    CONF_SSL_CERT_FILE_PATH,
    CONF_VERIFY_SSL,
    DOMAIN,
    LIST_VIRTUAL_DEVICES,
    VIRTUAL_DEVICE,
)
from custom_components.abbfreeathome_ci.entity import FreeAtHomeEntity
from custom_components.abbfreeathome_ci.helpers import async_get_via_device_kwargs
from homeassistant.config_entries import SOURCE_IGNORE, SOURCE_IMPORT, ConfigEntryState
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    STATE_UNAVAILABLE,
    Platform,
)
from homeassistant.core import HomeAssistant, ServiceValidationError
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)


@pytest.fixture
def mock_free_at_home():
    """Mock FreeAtHome instance."""

    async def ws_listen_coro():
        """Mock coroutine for ws_listen."""

    mock = MagicMock()
    mock.get_config = AsyncMock()
    mock.load = AsyncMock()
    mock.get_devices = MagicMock(return_value={})
    mock.get_channels_by_device = MagicMock(return_value=[])
    # Create coroutine lazily only when called
    mock.ws_listen = MagicMock(side_effect=ws_listen_coro)
    mock.ws_close = AsyncMock()
    mock.unload_device = MagicMock()
    mock.api = MagicMock()
    mock.api.virtualdevice = AsyncMock()
    return mock


@pytest.fixture
def mock_free_at_home_settings():
    """Mock FreeAtHomeSettings instance."""
    mock = MagicMock()
    mock.load = AsyncMock()
    mock.name = "Test SysAP"
    mock.version = "3.0.0"
    mock.hardware_version = "1.0"
    mock.serial_number = "TEST123456"
    return mock


async def test_async_setup_no_config(hass: HomeAssistant) -> None:
    """Test async_setup with no YAML config."""
    result = await async_setup(hass, {})
    assert result is True


async def test_async_setup_with_config(hass: HomeAssistant) -> None:
    """Test async_setup creates import flow from YAML config."""
    config = {
        DOMAIN: {
            CONF_HOST: "http://192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password",
        }
    }

    with patch.object(hass.config_entries.flow, "async_init") as mock_flow_init:
        result = await async_setup(hass, config)

    assert result is True
    mock_flow_init.assert_called_once_with(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data=config[DOMAIN],
    )


async def test_async_setup_entry_http(
    hass: HomeAssistant,
    mock_config_entry,
    mock_free_at_home,
    mock_free_at_home_settings,
) -> None:
    """Test successful setup of entry with HTTP."""
    # Add config entry to hass
    mock_config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHomeSettings",
            return_value=mock_free_at_home_settings,
        ),
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHome",
            return_value=mock_free_at_home,
        ),
        patch("custom_components.abbfreeathome_ci.FreeAtHomeApi") as mock_api_class,
        patch(
            "custom_components.abbfreeathome_ci.async_get_clientsession"
        ) as mock_session,
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            return_value=AsyncMock(),
        ),
    ):
        mock_session.return_value = MagicMock()
        mock_api_class.return_value = MagicMock()

        result = await async_setup_entry(hass, mock_config_entry)

    assert result is True
    assert DOMAIN in hass.data
    assert mock_config_entry.entry_id in hass.data[DOMAIN]
    mock_free_at_home_settings.load.assert_called_once()
    mock_free_at_home.get_config.assert_called_once()
    mock_free_at_home.load.assert_called_once()
    # Verify FreeAtHomeApi was instantiated with wait_for_result=False
    mock_api_class.assert_called_once()
    call_kwargs = mock_api_class.call_args.kwargs
    assert call_kwargs["wait_for_result"] is False


async def test_async_setup_entry_https_without_verification(
    hass: HomeAssistant, mock_free_at_home, mock_free_at_home_settings
) -> None:
    """Test setup logs warning for HTTPS without SSL verification."""
    https_entry = MockConfigEntry(
        version=1,
        minor_version=5,
        domain=DOMAIN,
        title="Test SysAP",
        data={
            CONF_SERIAL: "TEST123456",
            "name": "Test SysAP",
            CONF_HOST: "https://192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password",
            CONF_INCLUDE_ORPHAN_CHANNELS: False,
            CONF_INCLUDE_VIRTUAL_DEVICES: False,
            CONF_CREATE_SUBDEVICES: False,
            CONF_SSL_CERT_FILE_PATH: None,
            CONF_VERIFY_SSL: False,
        },
        source="user",
        unique_id="TEST123456",
        discovery_keys={},
        options={},
        subentries_data={},
    )
    # Add config entry to hass
    https_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHomeSettings",
            return_value=mock_free_at_home_settings,
        ),
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHome",
            return_value=mock_free_at_home,
        ),
        patch("custom_components.abbfreeathome_ci.FreeAtHomeApi") as mock_api_class,
        patch("custom_components.abbfreeathome_ci.async_get_clientsession"),
        patch("custom_components.abbfreeathome_ci._LOGGER") as mock_logger,
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            return_value=AsyncMock(),
        ),
    ):
        mock_api_class.return_value = MagicMock()
        result = await async_setup_entry(hass, https_entry)

    assert result is True
    mock_logger.warning.assert_called_once()
    assert "without SSL verification" in mock_logger.warning.call_args[0][0]
    # Verify FreeAtHomeApi was instantiated with wait_for_result=False
    mock_api_class.assert_called_once()
    call_kwargs = mock_api_class.call_args.kwargs
    assert call_kwargs["wait_for_result"] is False


async def test_async_setup_entry_https_with_verification(
    hass: HomeAssistant, mock_free_at_home, mock_free_at_home_settings
) -> None:
    """Test setup logs info for HTTPS with SSL verification."""
    https_entry = MockConfigEntry(
        version=1,
        minor_version=5,
        domain=DOMAIN,
        title="Test SysAP",
        data={
            CONF_SERIAL: "TEST123456",
            "name": "Test SysAP",
            CONF_HOST: "https://192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password",
            CONF_INCLUDE_ORPHAN_CHANNELS: False,
            CONF_INCLUDE_VIRTUAL_DEVICES: False,
            CONF_CREATE_SUBDEVICES: False,
            CONF_SSL_CERT_FILE_PATH: "/path/to/cert.pem",
            CONF_VERIFY_SSL: True,
        },
        source="user",
        unique_id="TEST123456",
        discovery_keys={},
        options={},
        subentries_data={},
    )
    # Add config entry to hass
    https_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHomeSettings",
            return_value=mock_free_at_home_settings,
        ),
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHome",
            return_value=mock_free_at_home,
        ),
        patch("custom_components.abbfreeathome_ci.FreeAtHomeApi") as mock_api_class,
        patch("custom_components.abbfreeathome_ci.async_get_clientsession"),
        patch("custom_components.abbfreeathome_ci._LOGGER") as mock_logger,
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            return_value=AsyncMock(),
        ),
    ):
        mock_api_class.return_value = MagicMock()
        result = await async_setup_entry(hass, https_entry)

    assert result is True
    mock_logger.info.assert_called_once()
    assert "SSL certificate verification enabled" in mock_logger.info.call_args[0][0]
    # Verify FreeAtHomeApi was instantiated with wait_for_result=False
    mock_api_class.assert_called_once()
    call_kwargs = mock_api_class.call_args.kwargs
    assert call_kwargs["wait_for_result"] is False


async def test_async_setup_entry_with_virtual_devices(
    hass: HomeAssistant, mock_free_at_home, mock_free_at_home_settings
) -> None:
    """Test setup includes virtual device interface when configured."""
    entry_with_virtual = MockConfigEntry(
        version=1,
        minor_version=5,
        domain=DOMAIN,
        title="Test SysAP",
        data={
            CONF_SERIAL: "TEST123456",
            "name": "Test SysAP",
            CONF_HOST: "http://192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password",
            CONF_INCLUDE_ORPHAN_CHANNELS: False,
            CONF_INCLUDE_VIRTUAL_DEVICES: True,
            CONF_CREATE_SUBDEVICES: False,
            CONF_SSL_CERT_FILE_PATH: None,
            CONF_VERIFY_SSL: False,
        },
        source="user",
        unique_id="TEST123456",
        discovery_keys={},
        options={},
        subentries_data={},
    )
    # Add config entry to hass
    entry_with_virtual.add_to_hass(hass)

    with (
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHomeSettings",
            return_value=mock_free_at_home_settings,
        ),
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHome",
            return_value=mock_free_at_home,
        ) as mock_fah_class,
        patch("custom_components.abbfreeathome_ci.async_get_clientsession"),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            return_value=AsyncMock(),
        ),
    ):
        result = await async_setup_entry(hass, entry_with_virtual)

    assert result is True
    # Verify Interface.VIRTUAL_DEVICE was included in interfaces
    call_kwargs = mock_fah_class.call_args[1]
    assert len(call_kwargs["interfaces"]) == 5  # 4 basic + 1 virtual


async def test_async_unload_entry(
    hass: HomeAssistant, mock_config_entry, mock_free_at_home
) -> None:
    """Test unloading a config entry."""
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    with patch(
        "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
        return_value=True,
    ):
        result = await async_unload_entry(hass, mock_config_entry)

    assert result is True
    mock_free_at_home.ws_close.assert_called_once()
    assert mock_config_entry.entry_id not in hass.data[DOMAIN]


async def test_async_remove_config_entry_device(
    hass: HomeAssistant, mock_config_entry, mock_free_at_home
) -> None:
    """Test removing a device from a config entry."""
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}

    mock_device_entry = MagicMock()
    mock_device_entry.identifiers = {(DOMAIN, "DEVICE123")}

    result = await async_remove_config_entry_device(
        hass, mock_config_entry, mock_device_entry
    )

    assert result is True
    mock_free_at_home.unload_device.assert_called_once_with("DEVICE123")


async def test_async_migrate_entry_from_v1_0(hass: HomeAssistant) -> None:
    """Test migration from version 1.0."""
    entry = MockConfigEntry(
        version=1,
        minor_version=0,
        domain=DOMAIN,
        title="Test",
        data={
            CONF_HOST: "http://192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password",
        },
        source="user",
        unique_id="TEST123",
        discovery_keys={},
        options={},
        subentries_data={},
    )
    # Add config entry to hass
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.version == 1
    assert entry.minor_version == 6
    assert entry.data[CONF_CREATE_UNRESPONSIVE_REPAIRS] is False
    assert entry.data[CONF_INCLUDE_ORPHAN_CHANNELS] is True
    assert entry.data[CONF_INCLUDE_VIRTUAL_DEVICES] is False
    assert entry.data[CONF_CREATE_SUBDEVICES] is False
    assert entry.data[CONF_SSL_CERT_FILE_PATH] is None
    assert entry.data[CONF_VERIFY_SSL] is False


async def test_async_migrate_entry_from_v1_2(hass: HomeAssistant) -> None:
    """Test migration from version 1.2."""
    entry = MockConfigEntry(
        version=1,
        minor_version=2,
        domain=DOMAIN,
        title="Test",
        data={
            CONF_HOST: "http://192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password",
            CONF_INCLUDE_ORPHAN_CHANNELS: True,
        },
        source="user",
        unique_id="TEST123",
        discovery_keys={},
        options={},
        subentries_data={},
    )
    # Add config entry to hass
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.version == 1
    assert entry.minor_version == 6
    assert entry.data[CONF_CREATE_UNRESPONSIVE_REPAIRS] is False
    assert entry.data[CONF_INCLUDE_VIRTUAL_DEVICES] is False
    assert entry.data[CONF_CREATE_SUBDEVICES] is False
    assert entry.data[CONF_SSL_CERT_FILE_PATH] is None
    assert entry.data[CONF_VERIFY_SSL] is False


async def test_async_migrate_entry_from_v1_4(hass: HomeAssistant) -> None:
    """Test migration from version 1.4 keeps existing settings."""
    entry = MockConfigEntry(
        version=1,
        minor_version=4,
        domain=DOMAIN,
        title="Test",
        data={
            CONF_HOST: "http://192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password",
            CONF_INCLUDE_ORPHAN_CHANNELS: True,
            CONF_INCLUDE_VIRTUAL_DEVICES: True,
            CONF_CREATE_SUBDEVICES: True,
        },
        source="user",
        unique_id="TEST123",
        discovery_keys={},
        options={},
        subentries_data={},
    )
    # Add config entry to hass
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.version == 1
    assert entry.minor_version == 6
    assert entry.data[CONF_CREATE_UNRESPONSIVE_REPAIRS] is False
    assert entry.data[CONF_SSL_CERT_FILE_PATH] is None
    assert entry.data[CONF_VERIFY_SSL] is False
    assert entry.data[CONF_INCLUDE_VIRTUAL_DEVICES] is True
    assert entry.data[CONF_CREATE_SUBDEVICES] is True


async def test_async_migrate_entry_from_v1_5(hass: HomeAssistant) -> None:
    """Test migration from version 1.5 keeps existing settings."""
    entry = MockConfigEntry(
        version=1,
        minor_version=5,
        domain=DOMAIN,
        title="Test",
        data={
            CONF_HOST: "http://192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password",
            CONF_INCLUDE_ORPHAN_CHANNELS: False,
            CONF_INCLUDE_VIRTUAL_DEVICES: True,
            CONF_CREATE_SUBDEVICES: True,
            CONF_SSL_CERT_FILE_PATH: "/existing/path.pem",
            CONF_VERIFY_SSL: True,
        },
        source="user",
        unique_id="TEST123",
        discovery_keys={},
        options={},
        subentries_data={},
    )
    # Add config entry to hass
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.version == 1
    assert entry.minor_version == 6
    assert entry.data[CONF_CREATE_UNRESPONSIVE_REPAIRS] is False
    assert entry.data[CONF_INCLUDE_ORPHAN_CHANNELS] is False
    assert entry.data[CONF_INCLUDE_VIRTUAL_DEVICES] is True
    assert entry.data[CONF_CREATE_SUBDEVICES] is True
    assert entry.data[CONF_SSL_CERT_FILE_PATH] == "/existing/path.pem"
    assert entry.data[CONF_VERIFY_SSL] is True


async def test_async_migrate_entry_future_version(hass: HomeAssistant) -> None:
    """Test migration fails for future versions."""
    entry = MockConfigEntry(
        version=2,
        minor_version=0,
        domain=DOMAIN,
        title="Test",
        data={},
        source="user",
        unique_id="TEST123",
    )

    result = await async_migrate_entry(hass, entry)

    assert result is False


async def test_async_migrate_entry_already_current(hass: HomeAssistant) -> None:
    """Test migration succeeds when already at current version."""
    entry = MockConfigEntry(
        version=1,
        minor_version=6,
        domain=DOMAIN,
        title="Test",
        data={
            CONF_HOST: "http://192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password",
            CONF_INCLUDE_ORPHAN_CHANNELS: True,
            CONF_INCLUDE_VIRTUAL_DEVICES: False,
            CONF_CREATE_SUBDEVICES: False,
            CONF_CREATE_UNRESPONSIVE_REPAIRS: True,
            CONF_SSL_CERT_FILE_PATH: None,
            CONF_VERIFY_SSL: False,
        },
        source="user",
        unique_id="TEST123",
        discovery_keys={},
        options={},
        subentries_data={},
    )
    # Add config entry to hass
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.version == 1
    assert entry.minor_version == 6
    # An already migrated entry keeps its setting.
    assert entry.data[CONF_CREATE_UNRESPONSIVE_REPAIRS] is True


async def test_async_setup_entry_with_devices(
    hass: HomeAssistant, mock_config_entry, mock_free_at_home_settings
) -> None:
    """Test setup registers devices with channels."""
    mock_config_entry.add_to_hass(hass)

    # Create mock device with channels
    mock_device = MagicMock()
    mock_device.device_serial = "DEVICE123"
    mock_device.display_name = "Test Device"
    mock_device.device_id = "HW123"
    mock_device.room_name = "Living Room"

    mock_channel = MagicMock()

    # Create FreeAtHome mock with device
    async def ws_listen_coro():
        pass

    mock_fah = MagicMock()
    mock_fah.get_config = AsyncMock()
    mock_fah.load = AsyncMock()
    mock_fah.get_devices = MagicMock(return_value={"DEVICE123": mock_device})
    mock_fah.get_channels_by_device = MagicMock(return_value=[mock_channel])
    mock_fah.ws_listen = MagicMock(return_value=ws_listen_coro())
    mock_fah.ws_close = AsyncMock()

    with (
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHomeSettings",
            return_value=mock_free_at_home_settings,
        ),
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHome",
            return_value=mock_fah,
        ),
        patch("custom_components.abbfreeathome_ci.async_get_clientsession"),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            return_value=AsyncMock(),
        ),
        patch("custom_components.abbfreeathome_ci.async_setup_service") as mock_service,
    ):
        result = await async_setup_entry(hass, mock_config_entry)

    assert result is True
    mock_service.assert_called_once()


async def test_async_setup_entry_device_via_device_id(
    hass: HomeAssistant, mock_config_entry, mock_free_at_home_settings
) -> None:
    """Test setup uses via_device_id when the device registry supports it."""
    mock_config_entry.add_to_hass(hass)

    # Create mock device with channels
    mock_device = MagicMock()
    mock_device.device_serial = "DEVICE123"
    mock_device.display_name = "Test Device"
    mock_device.device_id = "HW123"
    mock_device.room_name = "Living Room"

    mock_channel = MagicMock()

    # Create FreeAtHome mock with device
    async def ws_listen_coro():
        pass

    mock_fah = MagicMock()
    mock_fah.get_config = AsyncMock()
    mock_fah.load = AsyncMock()
    mock_fah.get_devices = MagicMock(return_value={"DEVICE123": mock_device})
    mock_fah.get_channels_by_device = MagicMock(return_value=[mock_channel])
    mock_fah.ws_listen = MagicMock(return_value=ws_listen_coro())
    mock_fah.ws_close = AsyncMock()

    # Simulate an HA core whose device registry already exposes
    # via_device_id by giving the mocked async_get_or_create a matching
    # signature.
    mock_device_registry = MagicMock()
    mock_device_registry.async_get_or_create.__signature__ = inspect.signature(
        lambda *, via_device_id=None, **kwargs: None
    )

    with (
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHomeSettings",
            return_value=mock_free_at_home_settings,
        ),
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHome",
            return_value=mock_fah,
        ),
        patch("custom_components.abbfreeathome_ci.async_get_clientsession"),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            return_value=AsyncMock(),
        ),
        patch("custom_components.abbfreeathome_ci.async_setup_service"),
        patch(
            "custom_components.abbfreeathome_ci.dr.async_get",
            return_value=mock_device_registry,
        ),
    ):
        result = await async_setup_entry(hass, mock_config_entry)

    assert result is True

    sysap_call, device_call = mock_device_registry.async_get_or_create.call_args_list
    sysap_device = mock_device_registry.async_get_device_by_identifier.return_value

    mock_device_registry.async_get_device_by_identifier.assert_called_once_with(
        (DOMAIN, mock_config_entry.data[CONF_SERIAL]), mock_config_entry.entry_id
    )
    assert "via_device_id" not in sysap_call.kwargs
    assert "via_device" not in sysap_call.kwargs
    assert device_call.kwargs["via_device_id"] == sysap_device.id
    assert "via_device" not in device_call.kwargs


async def test_async_setup_entry_device_via_device_fallback(
    hass: HomeAssistant, mock_config_entry, mock_free_at_home_settings
) -> None:
    """Test setup falls back to via_device on older device registries."""
    mock_config_entry.add_to_hass(hass)

    # Create mock device with channels
    mock_device = MagicMock()
    mock_device.device_serial = "DEVICE123"
    mock_device.display_name = "Test Device"
    mock_device.device_id = "HW123"
    mock_device.room_name = "Living Room"

    mock_channel = MagicMock()

    # Create FreeAtHome mock with device
    async def ws_listen_coro():
        pass

    mock_fah = MagicMock()
    mock_fah.get_config = AsyncMock()
    mock_fah.load = AsyncMock()
    mock_fah.get_devices = MagicMock(return_value={"DEVICE123": mock_device})
    mock_fah.get_channels_by_device = MagicMock(return_value=[mock_channel])
    mock_fah.ws_listen = MagicMock(return_value=ws_listen_coro())
    mock_fah.ws_close = AsyncMock()

    # Simulate an older HA core whose device registry only knows
    # via_device, by giving the mocked async_get_or_create a matching
    # signature without via_device_id.
    mock_device_registry = MagicMock()
    mock_device_registry.async_get_or_create.__signature__ = inspect.signature(
        lambda *, via_device=None, **kwargs: None
    )

    with (
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHomeSettings",
            return_value=mock_free_at_home_settings,
        ),
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHome",
            return_value=mock_fah,
        ),
        patch("custom_components.abbfreeathome_ci.async_get_clientsession"),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            return_value=AsyncMock(),
        ),
        patch("custom_components.abbfreeathome_ci.async_setup_service"),
        patch(
            "custom_components.abbfreeathome_ci.dr.async_get",
            return_value=mock_device_registry,
        ),
    ):
        result = await async_setup_entry(hass, mock_config_entry)

    assert result is True

    sysap_call, device_call = mock_device_registry.async_get_or_create.call_args_list

    assert "via_device_id" not in sysap_call.kwargs
    assert "via_device" not in sysap_call.kwargs
    assert device_call.kwargs["via_device"] == (DOMAIN, "TEST123456")
    assert "via_device_id" not in device_call.kwargs


async def test_async_setup_entry_missing_orphan_channels_key(
    hass: HomeAssistant, mock_free_at_home, mock_free_at_home_settings
) -> None:
    """Test setup handles missing include_orphan_channels key."""
    entry = MockConfigEntry(
        version=1,
        minor_version=5,
        domain=DOMAIN,
        title="Test SysAP",
        data={
            CONF_SERIAL: "TEST123456",
            "name": "Test SysAP",
            CONF_HOST: "http://192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password",
            # Missing CONF_INCLUDE_ORPHAN_CHANNELS
            CONF_INCLUDE_VIRTUAL_DEVICES: False,
            CONF_CREATE_SUBDEVICES: False,
            CONF_SSL_CERT_FILE_PATH: None,
            CONF_VERIFY_SSL: False,
        },
        source="user",
        unique_id="TEST123456",
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHomeSettings",
            return_value=mock_free_at_home_settings,
        ),
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHome",
            return_value=mock_free_at_home,
        ) as mock_fah_class,
        patch("custom_components.abbfreeathome_ci.async_get_clientsession"),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            return_value=AsyncMock(),
        ),
    ):
        result = await async_setup_entry(hass, entry)

    assert result is True
    # Verify include_orphan_channels defaults to True
    call_kwargs = mock_fah_class.call_args[1]
    assert call_kwargs["include_orphan_channels"] is True


async def test_async_setup_entry_missing_virtual_devices_key(
    hass: HomeAssistant, mock_free_at_home, mock_free_at_home_settings
) -> None:
    """Test setup handles missing include_virtual_devices key."""
    entry = MockConfigEntry(
        version=1,
        minor_version=5,
        domain=DOMAIN,
        title="Test SysAP",
        data={
            CONF_SERIAL: "TEST123456",
            "name": "Test SysAP",
            CONF_HOST: "http://192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password",
            CONF_INCLUDE_ORPHAN_CHANNELS: False,
            # Missing CONF_INCLUDE_VIRTUAL_DEVICES
            CONF_CREATE_SUBDEVICES: False,
            CONF_SSL_CERT_FILE_PATH: None,
            CONF_VERIFY_SSL: False,
        },
        source="user",
        unique_id="TEST123456",
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHomeSettings",
            return_value=mock_free_at_home_settings,
        ),
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHome",
            return_value=mock_free_at_home,
        ) as mock_fah_class,
        patch("custom_components.abbfreeathome_ci.async_get_clientsession"),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            return_value=AsyncMock(),
        ),
    ):
        result = await async_setup_entry(hass, entry)

    assert result is True
    # Verify only 4 interfaces (no virtual device)
    call_kwargs = mock_fah_class.call_args[1]
    assert len(call_kwargs["interfaces"]) == 4


async def test_async_setup_entry_https_url_conversion(
    hass: HomeAssistant, mock_free_at_home, mock_free_at_home_settings
) -> None:
    """Test that HTTPS URLs are converted to HTTP for device configuration."""
    https_entry = MockConfigEntry(
        version=1,
        minor_version=5,
        domain=DOMAIN,
        title="Test SysAP",
        data={
            CONF_SERIAL: "TEST123456",
            "name": "Test SysAP",
            CONF_HOST: "https://192.168.1.100:443/path",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password",
            CONF_INCLUDE_ORPHAN_CHANNELS: False,
            CONF_INCLUDE_VIRTUAL_DEVICES: False,
            CONF_CREATE_SUBDEVICES: False,
            CONF_SSL_CERT_FILE_PATH: "/path/to/cert.pem",
            CONF_VERIFY_SSL: True,
        },
        source="user",
        unique_id="TEST123456",
    )
    https_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHomeSettings",
            return_value=mock_free_at_home_settings,
        ),
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHome",
            return_value=mock_free_at_home,
        ),
        patch("custom_components.abbfreeathome_ci.async_get_clientsession"),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            return_value=AsyncMock(),
        ),
        patch("custom_components.abbfreeathome_ci.dr.async_get") as mock_dr,
    ):
        mock_device_registry = MagicMock()
        mock_dr.return_value = mock_device_registry

        result = await async_setup_entry(hass, https_entry)

    assert result is True
    # Verify device was registered with HTTP URL (path preserved)
    calls = mock_device_registry.async_get_or_create.call_args_list
    sysap_call = calls[0][1]
    assert sysap_call["configuration_url"] == "http://192.168.1.100/path"


async def _async_setup_entry_via_hass(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    mock_free_at_home: MagicMock,
    mock_free_at_home_settings: MagicMock,
) -> None:
    """Set up the entry through Home Assistant with the library patched."""
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHomeSettings",
            return_value=mock_free_at_home_settings,
        ),
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHome",
            return_value=mock_free_at_home,
        ),
        patch("custom_components.abbfreeathome_ci.FreeAtHomeApi"),
        patch("custom_components.abbfreeathome_ci.async_get_clientsession"),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.parametrize(
    "failing_call",
    [
        lambda settings, _: settings.load,
        lambda _, free_at_home: free_at_home.get_config,
        lambda _, free_at_home: free_at_home.load,
    ],
    ids=["settings_load", "get_config", "load"],
)
async def test_async_setup_entry_retries_when_sysap_unreachable(
    hass: HomeAssistant,
    mock_config_entry,
    mock_free_at_home,
    mock_free_at_home_settings,
    failing_call,
) -> None:
    """Test that setup is retried when any SysAP call cannot connect."""
    failing_call(
        mock_free_at_home_settings, mock_free_at_home
    ).side_effect = ClientConnectionError("http://192.168.1.100")

    await _async_setup_entry_via_hass(
        hass, mock_config_entry, mock_free_at_home, mock_free_at_home_settings
    )

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    # Home Assistant drops the trailing period of translated messages
    assert mock_config_entry.reason == (
        "The System Access Point at http://192.168.1.100 is not reachable or not "
        "ready yet"
    )
    assert mock_config_entry.entry_id not in hass.data.get(DOMAIN, {})


@pytest.mark.parametrize(
    ("error", "expected_state", "translation_key"),
    [
        (
            ClientConnectionError("http://192.168.1.100"),
            ConfigEntryState.SETUP_RETRY,
            "setup_cannot_connect",
        ),
        (
            ConnectionTimeoutException("http://192.168.1.100"),
            ConfigEntryState.SETUP_RETRY,
            "setup_cannot_connect",
        ),
        (
            InvalidApiResponseException(503),
            ConfigEntryState.SETUP_RETRY,
            "setup_cannot_connect",
        ),
        # aiohttp raises its total request timeout as plain TimeoutError
        (
            TimeoutError(),
            ConfigEntryState.SETUP_RETRY,
            "setup_cannot_connect",
        ),
        (
            InvalidHostException("192.168.1.100"),
            ConfigEntryState.SETUP_ERROR,
            "setup_invalid_host",
        ),
        (
            SslErrorException("http://192.168.1.100"),
            ConfigEntryState.SETUP_ERROR,
            "setup_ssl_error",
        ),
        (
            InvalidCredentialsException("installer"),
            ConfigEntryState.SETUP_ERROR,
            "setup_invalid_auth",
        ),
        (
            ForbiddenAuthException("/rest/configuration", 403),
            ConfigEntryState.SETUP_ERROR,
            "setup_invalid_auth",
        ),
    ],
)
async def test_async_setup_entry_sysap_errors(
    hass: HomeAssistant,
    mock_config_entry,
    mock_free_at_home,
    mock_free_at_home_settings,
    error,
    expected_state,
    translation_key,
) -> None:
    """Test that SysAP errors during setup map to the right entry state."""
    mock_free_at_home.get_config.side_effect = error

    await _async_setup_entry_via_hass(
        hass, mock_config_entry, mock_free_at_home, mock_free_at_home_settings
    )

    translations = json.loads(
        Path("custom_components/abbfreeathome_ci/translations/en.json").read_text(
            encoding="utf-8"
        )
    )
    assert mock_config_entry.state is expected_state
    message = translations["exceptions"][translation_key]["message"]
    assert mock_config_entry.reason == message.format(
        host="http://192.168.1.100"
    ).rstrip(".")
    mock_free_at_home.load.assert_not_awaited()


async def test_async_setup_service_already_registered(
    hass: HomeAssistant, mock_config_entry, mock_free_at_home_settings
) -> None:
    """Test setup skips service registration if already exists."""
    mock_config_entry.add_to_hass(hass)

    # Mock that service already exists (use VIRTUAL_DEVICE constant)
    hass.services.async_register(DOMAIN, VIRTUAL_DEVICE, lambda call: None)

    async def ws_listen_coro():
        pass

    mock_fah = MagicMock()
    mock_fah.get_config = AsyncMock()
    mock_fah.load = AsyncMock()
    mock_fah.get_devices = MagicMock(return_value={})
    mock_fah.get_channels_by_device = MagicMock(return_value=[])
    mock_fah.ws_listen = MagicMock(return_value=ws_listen_coro())
    mock_fah.ws_close = AsyncMock()

    with (
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHomeSettings",
            return_value=mock_free_at_home_settings,
        ),
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHome",
            return_value=mock_fah,
        ),
        patch("custom_components.abbfreeathome_ci.async_get_clientsession"),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            return_value=AsyncMock(),
        ),
        patch("custom_components.abbfreeathome_ci.async_setup_service") as mock_service,
    ):
        result = await async_setup_entry(hass, mock_config_entry)

    assert result is True
    # Service setup should not be called since service already exists
    mock_service.assert_not_called()


async def test_async_migrate_entry_ssl_fields_already_present(
    hass: HomeAssistant,
) -> None:
    """Test migration handles SSL fields when already present."""
    entry = MockConfigEntry(
        version=1,
        minor_version=4,
        domain=DOMAIN,
        title="Test",
        data={
            CONF_HOST: "http://192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password",
            CONF_INCLUDE_ORPHAN_CHANNELS: True,
            CONF_INCLUDE_VIRTUAL_DEVICES: False,
            CONF_CREATE_SUBDEVICES: False,
            CONF_SSL_CERT_FILE_PATH: "/existing/path.pem",
            CONF_VERIFY_SSL: True,
        },
        source="user",
        unique_id="TEST123",
    )
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.version == 1
    assert entry.minor_version == 6
    assert entry.data[CONF_CREATE_UNRESPONSIVE_REPAIRS] is False
    # SSL fields should be preserved
    assert entry.data[CONF_SSL_CERT_FILE_PATH] == "/existing/path.pem"
    assert entry.data[CONF_VERIFY_SSL] is True


async def test_virtual_device_service(hass: HomeAssistant) -> None:
    """Test virtual_device service call."""
    # Create a mock entry and add to hass
    entry = MockConfigEntry(
        version=1,
        minor_version=5,
        domain=DOMAIN,
        title="Test SysAP",
        data={
            CONF_SERIAL: "TEST123456",
            "name": "Test SysAP",
            CONF_HOST: "http://192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password",
            CONF_INCLUDE_ORPHAN_CHANNELS: False,
            CONF_INCLUDE_VIRTUAL_DEVICES: False,
            CONF_CREATE_SUBDEVICES: False,
            CONF_SSL_CERT_FILE_PATH: None,
            CONF_VERIFY_SSL: False,
        },
        source="user",
        unique_id="TEST123456",
    )
    entry.add_to_hass(hass)

    # Create mock FreeAtHome object
    mock_fah = MagicMock()
    mock_fah.api.virtualdevice = AsyncMock(return_value={"status": "success"})
    hass.data[DOMAIN] = {entry.entry_id: mock_fah}

    # Setup the service
    await async_setup_service(hass)

    # Test successful service call
    result = await hass.services.async_call(
        DOMAIN,
        "virtual_device",
        {
            "serial": "DEVICE123",
            "type": "light",
            "ttl": 300,
            "displayname": "Test Light",
            "flavor": "basic",
            "capabilities": [1, 2],
        },
        blocking=True,
        return_response=True,
    )

    assert result == {"status": "success"}
    mock_fah.api.virtualdevice.assert_called_once()

    # Test service call with BadRequestException
    mock_fah.api.virtualdevice = AsyncMock(
        side_effect=BadRequestException("Invalid request")
    )

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            "virtual_device",
            {
                "serial": "DEVICE123",
                "type": "light",
                "ttl": 300,
            },
            blocking=True,
            return_response=True,
        )

    assert "Invalid request" in str(exc_info.value)


@pytest.mark.parametrize(
    "ttl",
    [None, -1, 0, 180, 600, 86400, "-1", "0", "180", "300", "3600", "86400", "181"],
)
async def test_virtual_device_service_minimal_data(
    hass: HomeAssistant, ttl: int | str | None
) -> None:
    """Test virtual_device defaults TTL without overriding explicit values."""
    # Create a mock entry and add to hass
    entry = MockConfigEntry(
        version=1,
        minor_version=5,
        domain=DOMAIN,
        title="Test SysAP",
        data={
            CONF_SERIAL: "TEST123456",
            "name": "Test SysAP",
            CONF_HOST: "http://192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password",
            CONF_INCLUDE_ORPHAN_CHANNELS: False,
            CONF_INCLUDE_VIRTUAL_DEVICES: False,
            CONF_CREATE_SUBDEVICES: False,
            CONF_SSL_CERT_FILE_PATH: None,
            CONF_VERIFY_SSL: False,
        },
        source="user",
        unique_id="TEST123456",
    )
    entry.add_to_hass(hass)

    # Create mock FreeAtHome object
    mock_fah = MagicMock()
    mock_fah.api.virtualdevice = AsyncMock(return_value={"status": "ok"})
    hass.data[DOMAIN] = {entry.entry_id: mock_fah}

    # Setup the service
    await async_setup_service(hass)

    # Test service call with only required fields
    result = await hass.services.async_call(
        DOMAIN,
        "virtual_device",
        {
            "serial": "DEVICE456",
            "type": "switch",
            **({"ttl": ttl} if ttl is not None else {}),
        },
        blocking=True,
        return_response=True,
    )

    assert result == {"status": "ok"}

    # Verify the call was made with correct structure
    call_args = mock_fah.api.virtualdevice.call_args
    assert call_args[1]["serial"] == "DEVICE456"
    assert call_args[1]["data"]["type"] == "switch"
    assert call_args[1]["data"]["properties"]["ttl"] == (
        -1 if ttl is None else int(ttl)
    )
    # Optional fields should not be in data
    assert "displayname" not in call_args[1]["data"]["properties"]
    assert "flavor" not in call_args[1]["data"]["properties"]
    assert "capabilities" not in call_args[1]["data"]["properties"]


@pytest.mark.parametrize(
    ("device_type", "overrides", "energy_properties"),
    [
        (
            "EnergyMeterv2",
            {},
            {"flavor": "E", "capabilities": [16, 17, 18, 19, 22, 28]},
        ),
        (
            "EnergyMeterv2",
            {"flavor": "custom"},
            {"flavor": "custom", "capabilities": [16, 17, 18, 19, 22, 28]},
        ),
        (
            "EnergyMeterv2",
            {"capabilities": [16]},
            {"flavor": "E", "capabilities": [16]},
        ),
        (
            "EnergyMeterv2",
            {"flavor": "custom", "capabilities": []},
            {"flavor": "custom", "capabilities": []},
        ),
        ("WeatherStation", {}, {}),
        ("SwitchingActuator", {}, {}),
        ("DimActuator", {}, {}),
        ("BinarySensor", {}, {}),
        ("WindowSensor", {}, {}),
        ("RTC", {}, {}),
        ("Weather-BrightnessSensor", {}, {}),
        ("Weather-RainSensor", {}, {}),
        ("Weather-TemperatureSensor", {}, {}),
        ("Weather-WindSensor", {}, {}),
        ("AirQualityTemperature", {}, {}),
        ("custom", {}, {}),
    ],
)
async def test_virtual_device_service_type_defaults(
    hass: HomeAssistant, mock_config_entry, device_type, overrides, energy_properties
) -> None:
    """Apply energy presets only to energy meters and preserve explicit overrides."""
    mock_config_entry.add_to_hass(hass)
    original_data = dict(mock_config_entry.data)
    mock_fah = MagicMock()
    mock_fah.api.virtualdevice = AsyncMock(return_value={"DEVICE123": "VIRTUAL123"})
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_fah}
    await async_setup_service(hass)

    result = await hass.services.async_call(
        DOMAIN,
        "virtual_device",
        {"serial": "DEVICE123", "type": device_type, **overrides},
        blocking=True,
        return_response=True,
    )

    assert result == {"DEVICE123": "VIRTUAL123"}
    mock_fah.api.virtualdevice.assert_awaited_once_with(
        serial="DEVICE123",
        data={"type": device_type, "properties": {"ttl": -1, **energy_properties}},
    )
    assert mock_config_entry.data == original_data


@pytest.fixture
async def virtual_device_service(
    hass: HomeAssistant, mock_config_entry, mock_free_at_home
):
    """Register the service with one configured, available SysAP."""
    mock_config_entry.add_to_hass(hass)
    mock_free_at_home.api.virtualdevice.return_value = {"status": "ok"}
    hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_free_at_home}
    await async_setup_service(hass)
    return mock_free_at_home


@pytest.mark.parametrize("native_id", ["x", "A" * 64, "ha-Virtual_switch-01"])
async def test_virtual_device_accepts_native_id_boundaries(
    hass: HomeAssistant, virtual_device_service, native_id: str
) -> None:
    """Forward valid original IDs unchanged, including the minimum and maximum lengths."""
    await hass.services.async_call(
        DOMAIN,
        VIRTUAL_DEVICE,
        {"serial": native_id, "type": "SwitchingActuator"},
        blocking=True,
        return_response=True,
    )
    assert (
        virtual_device_service.api.virtualdevice.await_args.kwargs["serial"]
        == native_id
    )


@pytest.mark.parametrize(
    "native_id", ["", "a" * 65, "with space", "path/id", "ha_test\n", "h\u00e4_test"]
)
async def test_virtual_device_rejects_invalid_native_ids(
    hass: HomeAssistant, virtual_device_service, native_id: str
) -> None:
    """Reject IDs outside the API's nativeId format before making an upsert."""
    with pytest.raises(vol.Invalid, match="Virtual device ID"):
        await hass.services.async_call(
            DOMAIN,
            VIRTUAL_DEVICE,
            {"serial": native_id, "type": "SwitchingActuator"},
            blocking=True,
            return_response=True,
        )
    virtual_device_service.api.virtualdevice.assert_not_awaited()


@pytest.mark.parametrize("ttl", [-2, 1, 179, 86401, "1", "179", "invalid"])
async def test_virtual_device_rejects_invalid_lifetimes(
    hass: HomeAssistant, virtual_device_service, ttl: int | str
) -> None:
    """Custom dropdown values must still satisfy the API's lifetime ranges."""
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            VIRTUAL_DEVICE,
            {"serial": "ha-test", "type": "SwitchingActuator", "ttl": ttl},
            blocking=True,
            return_response=True,
        )
    virtual_device_service.api.virtualdevice.assert_not_awaited()


@pytest.mark.parametrize(
    ("target", "unload_first"), [("first", False), ("second", False), ("second", True)]
)
async def test_virtual_device_routes_to_selected_sysap(
    hass: HomeAssistant,
    mock_config_entry,
    virtual_device_service,
    target: str,
    unload_first: bool,
) -> None:
    """Route at call time, even after the SysAP that registered the service unloads."""
    second_entry = MockConfigEntry(domain=DOMAIN, title="Second SysAP", data={})
    second_entry.add_to_hass(hass)
    second_client = MagicMock()
    second_client.api.virtualdevice = AsyncMock(return_value={"status": "second"})
    hass.data[DOMAIN][second_entry.entry_id] = second_client
    if unload_first:
        hass.data[DOMAIN].pop(mock_config_entry.entry_id)
    selected_entry = mock_config_entry if target == "first" else second_entry
    selected_client = virtual_device_service if target == "first" else second_client
    other_client = second_client if target == "first" else virtual_device_service

    result = await hass.services.async_call(
        DOMAIN,
        VIRTUAL_DEVICE,
        {
            "config_entry_id": selected_entry.entry_id,
            "serial": "ha-test",
            "type": "SwitchingActuator",
        },
        blocking=True,
        return_response=True,
    )

    assert result == {"status": "ok" if target == "first" else "second"}
    selected_client.api.virtualdevice.assert_awaited_once_with(
        serial="ha-test", data={"type": "SwitchingActuator", "properties": {"ttl": -1}}
    )
    other_client.api.virtualdevice.assert_not_awaited()


@pytest.mark.parametrize("second_loaded", [False, True])
async def test_virtual_device_requires_sysap_for_multiple_entries(
    hass: HomeAssistant, virtual_device_service, second_loaded: bool
) -> None:
    """Never silently choose another configured SysAP when one is unavailable."""
    second_entry = MockConfigEntry(domain=DOMAIN, title="Second SysAP", data={})
    second_entry.add_to_hass(hass)
    second_client = MagicMock()
    second_client.api.virtualdevice = AsyncMock()
    if second_loaded:
        hass.data[DOMAIN][second_entry.entry_id] = second_client
    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            VIRTUAL_DEVICE,
            {"serial": "ha-test", "type": "SwitchingActuator"},
            blocking=True,
            return_response=True,
        )
    assert exc_info.value.translation_key == "virtual_device_sysap_required"
    virtual_device_service.api.virtualdevice.assert_not_awaited()
    second_client.api.virtualdevice.assert_not_awaited()


@pytest.mark.parametrize(
    ("target", "error"),
    [
        ("missing", "virtual_device_sysap_invalid"),
        ("foreign", "virtual_device_sysap_invalid"),
        ("unloaded", "virtual_device_sysap_unavailable"),
    ],
)
async def test_virtual_device_rejects_invalid_or_unavailable_sysap(
    hass: HomeAssistant, virtual_device_service, target: str, error: str
) -> None:
    """Reject invalid selections rather than falling back to an available SysAP."""
    entry_id = "missing"
    if target != "missing":
        entry = MockConfigEntry(
            domain="other_integration" if target == "foreign" else DOMAIN,
            title="Another integration",
            data={},
        )
        entry.add_to_hass(hass)
        entry_id = entry.entry_id
    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            VIRTUAL_DEVICE,
            {
                "config_entry_id": entry_id,
                "serial": "ha-test",
                "type": "SwitchingActuator",
            },
            blocking=True,
            return_response=True,
        )
    assert exc_info.value.translation_key == error
    virtual_device_service.api.virtualdevice.assert_not_awaited()


async def test_virtual_device_after_all_sysaps_unload(
    hass: HomeAssistant, virtual_device_service
) -> None:
    """Report unavailability instead of raising a stale-entry lookup error."""
    hass.data.pop(DOMAIN)
    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            VIRTUAL_DEVICE,
            {"serial": "ha-test", "type": "SwitchingActuator"},
            blocking=True,
            return_response=True,
        )
    assert exc_info.value.translation_key == "virtual_device_sysap_unavailable"
    virtual_device_service.api.virtualdevice.assert_not_awaited()


async def test_virtual_device_ignores_ignored_discoveries(
    hass: HomeAssistant, virtual_device_service
) -> None:
    """An ignored discovery is not another configured target requiring selection."""
    ignored = MockConfigEntry(domain=DOMAIN, source=SOURCE_IGNORE, data={})
    ignored.add_to_hass(hass)
    result = await hass.services.async_call(
        DOMAIN,
        VIRTUAL_DEVICE,
        {"serial": "ha-test", "type": "SwitchingActuator"},
        blocking=True,
        return_response=True,
    )
    assert result == {"status": "ok"}
    virtual_device_service.api.virtualdevice.assert_awaited_once()


async def test_list_virtual_devices(
    hass: HomeAssistant, mock_config_entry, virtual_device_service
) -> None:
    """List only virtual devices, sorted by virtual device ID, with their channels."""
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, CONF_INCLUDE_VIRTUAL_DEVICES: True},
    )
    floorplan = Floorplan.from_config(
        {"floorplan": {"floors": {"01": {"name": "Ground", "rooms": {}}}}}
    )
    floorplan_rooms = Floorplan.from_config(
        {
            "floorplan": {
                "floors": {"01": {"name": "Ground", "rooms": {"02": {"name": "Hall"}}}}
            }
        }
    )
    switch = Device(
        "6000AAAA0002",
        "0002",
        "Virtual switch",
        interface=Interface.VIRTUAL_DEVICE,
        api=MagicMock(),
        native_id="ha-switch",
        floor_name="Ground",
        channels_data={
            "ch0001": {"functionID": "7"},
            "ch0000": {
                "functionID": "7",
                "displayName": "Lamp",
                "floor": "01",
                "room": "02",
            },
        },
    )
    switch.load_channels(floorplan_rooms)
    unplaced = Device(
        "6000AAAA0001",
        "0001",
        "Unplaced",
        interface=Interface.VIRTUAL_DEVICE,
        api=MagicMock(),
        unresponsive=True,
    )
    unplaced.load_channels(floorplan)
    virtual_device_service.get_devices.return_value = {
        "ABB700000001": _device(),
        "6000AAAA0002": switch,
        "6000AAAA0001": unplaced,
    }

    result = await hass.services.async_call(
        DOMAIN, LIST_VIRTUAL_DEVICES, {}, blocking=True, return_response=True
    )

    assert result == {
        "virtual_devices": [
            {
                "native_id": None,
                "serial": "6000AAAA0001",
                "display_name": "Unplaced",
                "floor": None,
                "room": None,
                "unresponsive": True,
                "channels": [],
            },
            {
                "native_id": "ha-switch",
                "serial": "6000AAAA0002",
                "display_name": "Virtual switch",
                "floor": "Ground",
                "room": None,
                "unresponsive": False,
                "channels": [
                    {
                        "channel_id": "ch0000",
                        "channel_name": "Lamp",
                        "channel_type": "VirtualSwitchActuator",
                        "floor": "Ground",
                        "room": "Hall",
                    },
                    {
                        "channel_id": "ch0001",
                        "channel_name": "Channel ch0001",
                        "channel_type": "VirtualSwitchActuator",
                        "floor": "Ground",
                        "room": None,
                    },
                ],
            },
        ]
    }


async def test_list_virtual_devices_requires_virtual_devices_option(
    hass: HomeAssistant, virtual_device_service
) -> None:
    """Explain how to enable virtual devices instead of returning an empty list."""
    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN, LIST_VIRTUAL_DEVICES, {}, blocking=True, return_response=True
        )
    assert exc_info.value.translation_key == "list_virtual_devices_disabled"
    virtual_device_service.get_devices.assert_not_called()


async def test_async_setup_entry_device_without_channels(
    hass: HomeAssistant, mock_config_entry, mock_free_at_home_settings
) -> None:
    """Test setup skips device registration for devices without channels."""
    mock_config_entry.add_to_hass(hass)

    # Create mock device without channels
    mock_device = MagicMock()
    mock_device.device_serial = "DEVICE999"
    mock_device.display_name = "Empty Device"

    # Create FreeAtHome mock with device but no channels
    async def ws_listen_coro():
        pass

    mock_fah = MagicMock()
    mock_fah.get_config = AsyncMock()
    mock_fah.load = AsyncMock()
    mock_fah.get_devices = MagicMock(return_value={"DEVICE999": mock_device})
    mock_fah.get_channels_by_device = MagicMock(return_value=[])  # No channels
    mock_fah.ws_listen = MagicMock(return_value=ws_listen_coro())
    mock_fah.ws_close = AsyncMock()

    with (
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHomeSettings",
            return_value=mock_free_at_home_settings,
        ),
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHome",
            return_value=mock_fah,
        ),
        patch("custom_components.abbfreeathome_ci.async_get_clientsession"),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            return_value=AsyncMock(),
        ),
        patch("custom_components.abbfreeathome_ci.dr.async_get") as mock_dr,
    ):
        mock_device_registry = MagicMock()
        mock_dr.return_value = mock_device_registry

        result = await async_setup_entry(hass, mock_config_entry)

    assert result is True
    # Verify only SysAP was registered (not the device without channels)
    assert mock_device_registry.async_get_or_create.call_count == 1


async def test_async_migrate_entry_from_v1_1(hass: HomeAssistant) -> None:
    """Test migration from version 1.1 through all intermediate versions to 1.5."""
    entry = MockConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test",
        data={
            CONF_HOST: "http://192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password",
        },
        source="user",
        unique_id="TEST123",
    )
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.version == 1
    assert entry.minor_version == 6
    assert entry.data[CONF_CREATE_UNRESPONSIVE_REPAIRS] is False
    # v1.1 -> v1.2 adds orphan channels
    assert entry.data[CONF_INCLUDE_ORPHAN_CHANNELS] is True
    # Then continues to v1.3, v1.4, v1.5
    assert entry.data[CONF_INCLUDE_VIRTUAL_DEVICES] is False
    assert entry.data[CONF_CREATE_SUBDEVICES] is False
    assert entry.data[CONF_SSL_CERT_FILE_PATH] is None
    assert entry.data[CONF_VERIFY_SSL] is False


async def test_async_migrate_entry_from_v1_3(hass: HomeAssistant) -> None:
    """Test migration from version 1.3 through remaining versions to 1.6."""
    entry = MockConfigEntry(
        version=1,
        minor_version=3,
        domain=DOMAIN,
        title="Test",
        data={
            CONF_HOST: "http://192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password",
            CONF_INCLUDE_ORPHAN_CHANNELS: True,
            CONF_INCLUDE_VIRTUAL_DEVICES: True,
        },
        source="user",
        unique_id="TEST123",
    )
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.version == 1
    assert entry.minor_version == 6
    assert entry.data[CONF_CREATE_UNRESPONSIVE_REPAIRS] is False
    # v1.3 -> v1.4 adds create_subdevices and keeps virtual devices
    assert entry.data[CONF_INCLUDE_VIRTUAL_DEVICES] is True
    assert entry.data[CONF_CREATE_SUBDEVICES] is False
    # Then continues to v1.5
    assert entry.data[CONF_SSL_CERT_FILE_PATH] is None
    assert entry.data[CONF_VERIFY_SSL] is False


async def test_async_unload_entry_failure(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test unload entry when platform unload fails."""
    mock_config_entry.add_to_hass(hass)

    # Create mock FreeAtHome object
    mock_fah = MagicMock()
    mock_fah.ws_close = AsyncMock()
    hass.data.setdefault(DOMAIN, {})[mock_config_entry.entry_id] = mock_fah

    with patch(
        "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
        return_value=False,  # Simulate unload failure
    ):
        result = await async_unload_entry(hass, mock_config_entry)

    assert result is False
    # Verify ws_close was still called
    mock_fah.ws_close.assert_called_once()
    # Verify entry data was NOT removed (because unload failed)
    assert mock_config_entry.entry_id in hass.data[DOMAIN]


async def _setup_with_channels(
    hass: HomeAssistant, entry, settings, channels: list
) -> MagicMock:
    """Set up the integration with a mocked FreeAtHome holding mutable channels."""

    async def ws_listen_coro():
        """Mock coroutine for ws_listen."""

    mock_fah = MagicMock()
    mock_fah.channels = channels
    mock_fah.get_config = AsyncMock()
    mock_fah.load = AsyncMock()
    mock_fah.ws_listen = MagicMock(side_effect=ws_listen_coro)
    mock_fah.ws_close = AsyncMock()
    mock_fah.get_devices = MagicMock(
        side_effect=lambda: {
            channel.device_serial: channel.device for channel in channels
        }
    )
    mock_fah.get_channels_by_device = MagicMock(
        side_effect=lambda serial: [c for c in channels if c.device_serial == serial]
    )
    mock_fah.get_channels_by_class = MagicMock(
        side_effect=lambda channel_class: [
            c for c in channels if type(c) is channel_class
        ]
    )
    if hass.config_entries.async_get_entry(entry.entry_id) is None:
        entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.abbfreeathome_ci.FreeAtHomeSettings",
            return_value=settings,
        ),
        patch("custom_components.abbfreeathome_ci.FreeAtHome", return_value=mock_fah),
        patch("custom_components.abbfreeathome_ci.FreeAtHomeApi"),
        patch("custom_components.abbfreeathome_ci.async_get_clientsession"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return mock_fah


@pytest.fixture
def lifecycle_platforms(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load only the platforms used by the lifecycle tests' channels."""
    monkeypatch.setattr(
        "custom_components.abbfreeathome_ci.PLATFORMS",
        [Platform.BUTTON, Platform.SENSOR],
    )


@pytest.fixture
async def loaded_free_at_home(
    hass: HomeAssistant,
    mock_config_entry,
    mock_free_at_home_settings,
    lifecycle_platforms,
) -> MagicMock:
    """Set up the integration without any channels."""
    return await _setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, []
    )


def _trigger(device: Device, channel_id: str = "ch0000", parameters=None) -> Trigger:
    """Build a real Trigger channel (button entity)."""
    return Trigger(
        device, channel_id, f"Trigger {channel_id}", {}, {}, parameters or {}
    )


def _device(serial: str = "ABB700000001", parameters=None) -> Device:
    """Build a real free@home device."""
    return Device(
        serial,
        "1234",
        "Runtime Device",
        api=MagicMock(),
        room_name="Hall",
        parameters=parameters,
    )


def _devices_changed(mock_fah, event: DevicesChangedEvent) -> None:
    """Invoke the registered devices-changed callback."""
    mock_fah.register_devices_changed_callback.call_args.args[0](event)


async def test_runtime_device_added_unavailable_and_removed(
    hass: HomeAssistant,
    mock_config_entry,
    loaded_free_at_home,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test a device added at runtime, its availability, and its removal."""
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    device = _device()
    channel = _trigger(device)
    loaded_free_at_home.channels.append(channel)

    _devices_changed(
        loaded_free_at_home,
        DevicesChangedEvent(added_devices=(device,), added_channels=(channel,)),
    )
    # A repeated channel must not create a duplicate entity.
    _devices_changed(
        loaded_free_at_home, DevicesChangedEvent(added_channels=(channel,))
    )
    await hass.async_block_till_done()

    device_entry = device_registry.async_get_device(
        identifiers={(DOMAIN, "ABB700000001")}
    )
    assert device_entry is not None
    sysap_entry = device_registry.async_get_device(identifiers={(DOMAIN, "TEST123456")})
    assert device_entry.via_device_id == sysap_entry.id
    entities = er.async_entries_for_device(entity_registry, device_entry.id)
    assert len(entities) == 1
    assert "does not generate unique IDs" not in caplog.text
    entity_id = entities[0].entity_id
    assert hass.states.get(entity_id).state != STATE_UNAVAILABLE

    device.update_unresponsive(True)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    device.update_unresponsive(False)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state != STATE_UNAVAILABLE

    sub_device = device_registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={(DOMAIN, "ABB700000001_ch0000")},
        **async_get_via_device_kwargs(hass, mock_config_entry.entry_id, "ABB700000001"),
    )
    _devices_changed(
        loaded_free_at_home,
        DevicesChangedEvent(removed_device_serials=("ABB700000001", "UNKNOWN")),
    )
    await hass.async_block_till_done()

    assert device_registry.async_get(device_entry.id) is None
    assert device_registry.async_get(sub_device.id) is None
    assert device_registry.async_get(sysap_entry.id) is not None
    assert entity_registry.async_get(entity_id) is None
    assert hass.states.get(entity_id) is None


async def test_sub_devices_linked_to_parent_device(
    hass: HomeAssistant,
    mock_config_entry,
    mock_free_at_home_settings,
    lifecycle_platforms,
) -> None:
    """Test channel sub-devices are linked to their device and removed with it.

    An existing sub-device keeps its device id, area, and user-defined name. With
    HA 2026.9+ sub-devices are child devices named after their channel.
    """
    entry = MockConfigEntry(
        version=mock_config_entry.version,
        minor_version=mock_config_entry.minor_version,
        domain=DOMAIN,
        data={**mock_config_entry.data, CONF_CREATE_SUBDEVICES: True},
        unique_id=mock_config_entry.unique_id,
    )
    entry.add_to_hass(hass)
    device = _device()
    for channel_id in ("ch0000", "ch0001"):
        device.channels[channel_id] = _trigger(device, channel_id)
    assert device.is_multi_device

    # Registry entries left by an earlier version linking sub-devices with via_device.
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "ABB700000001")}
    )
    old_sub_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "ABB700000001_ch0000")},
        name="Runtime Device (ch0000)",
        **async_get_via_device_kwargs(hass, entry.entry_id, "ABB700000001"),
    )
    # Settings made by the user must survive the conversion.
    area = ar.async_get(hass).async_create("Living room")
    device_registry.async_update_device(
        old_sub_device.id, area_id=area.id, name_by_user="Ceiling light"
    )
    child_devices_supported = hasattr(dr, "ChildDeviceInfo")
    if child_devices_supported:
        # Like a restart, so the earlier registration can be converted.
        device_registry.async_config_entry_unloaded(entry.entry_id)

    mock_fah = await _setup_with_channels(
        hass, entry, mock_free_at_home_settings, list(device.channels.values())
    )

    parent_device = next(
        _device_entry
        for _device_entry in dr.async_entries_for_config_entry(
            device_registry, entry.entry_id
        )
        if (DOMAIN, "ABB700000001") in _device_entry.identifiers
    )
    sub_devices = [
        device_registry.async_get(_device_id)
        for _device_id in {
            _entity.device_id
            for _entity in er.async_entries_for_config_entry(
                er.async_get(hass), entry.entry_id
            )
        }
    ]
    assert len(sub_devices) == 2
    for sub_device in sub_devices:
        ((_, sub_device_serial),) = sub_device.identifiers
        channel_id = sub_device_serial.removeprefix("ABB700000001_")
        if channel_id == "ch0000":
            assert sub_device.id == old_sub_device.id
            assert sub_device.area_id == area.id
            assert sub_device.name_by_user == "Ceiling light"
        if child_devices_supported:
            assert sub_device.parent_device_id == parent_device.id
            assert sub_device.name == channel_id
        else:
            assert sub_device.via_device_id == parent_device.id
            assert sub_device.name == f"Runtime Device ({channel_id})"

    _devices_changed(
        mock_fah, DevicesChangedEvent(removed_device_serials=("ABB700000001",))
    )
    await hass.async_block_till_done()

    assert device_registry.async_get(parent_device.id) is None
    for sub_device in sub_devices:
        assert device_registry.async_get(sub_device.id) is None


async def test_runtime_channel_placed_later(
    hass: HomeAssistant, loaded_free_at_home
) -> None:
    """Test a device without visible channels appears once a channel is placed."""
    device_registry = dr.async_get(hass)
    device = _device()

    _devices_changed(loaded_free_at_home, DevicesChangedEvent(added_devices=(device,)))
    await hass.async_block_till_done()
    assert (
        device_registry.async_get_device(identifiers={(DOMAIN, "ABB700000001")}) is None
    )

    channel = _trigger(device)
    loaded_free_at_home.channels.append(channel)
    _devices_changed(
        loaded_free_at_home, DevicesChangedEvent(added_channels=(channel,))
    )
    await hass.async_block_till_done()

    device_entry = device_registry.async_get_device(
        identifiers={(DOMAIN, "ABB700000001")}
    )
    assert device_entry.name == "Runtime Device"
    assert device_entry.area_id == "hall"
    assert er.async_entries_for_device(er.async_get(hass), device_entry.id)


async def test_runtime_device_adds_parameter_sensor(
    hass: HomeAssistant, mock_config_entry, loaded_free_at_home
) -> None:
    """Test a device added at runtime gets one parameter sensor."""
    device = _device()
    channel = _trigger(device, parameters={"par0001": "0"})
    loaded_free_at_home.channels.append(channel)

    # The repeated channel is already exposed and must not change the sensor.
    for _ in range(2):
        _devices_changed(
            loaded_free_at_home, DevicesChangedEvent(added_channels=(channel,))
        )
        await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    sensors = [
        entry
        for entry in er.async_entries_for_config_entry(
            entity_registry, mock_config_entry.entry_id
        )
        if entry.domain == "sensor"
    ]
    assert [entry.unique_id for entry in sensors] == ["ABB700000001_parameters"]
    attributes = hass.states.get(sensors[0].entity_id).attributes
    assert list(attributes["channel_parameters"]) == ["ch0000"]
    assert attributes["channel_parameters"]["ch0000"]["parameters"] == {
        "PID_LED_DAY_BRIGHTNESS": "0"
    }


async def test_runtime_channels_while_addition_pending(
    hass: HomeAssistant,
    mock_config_entry,
    loaded_free_at_home,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test notifications arriving before entities are added create no duplicates."""
    entity_registry = er.async_get(hass)
    device = _device()
    first = _trigger(device, "ch0000", parameters={"par0001": "0"})
    second = _trigger(device, "ch0001", parameters={"par0002": "1"})
    loaded_free_at_home.channels.append(first)

    release = asyncio.Event()
    added_to_hass = FreeAtHomeEntity.async_added_to_hass

    async def _delayed_added_to_hass(entity: FreeAtHomeEntity) -> None:
        await release.wait()
        await added_to_hass(entity)

    with patch.object(FreeAtHomeEntity, "async_added_to_hass", _delayed_added_to_hass):
        for channels in ((first,), (first,), (second,)):
            if channels == (second,):
                loaded_free_at_home.channels.append(second)
            _devices_changed(
                loaded_free_at_home, DevicesChangedEvent(added_channels=channels)
            )
            for _ in range(5):
                await asyncio.sleep(0)
        release.set()
        await hass.async_block_till_done()

    assert "does not generate unique IDs" not in caplog.text
    assert "already exists" not in caplog.text
    assert sorted(
        entry.unique_id
        for entry in er.async_entries_for_config_entry(
            entity_registry, mock_config_entry.entry_id
        )
    ) == [
        "ABB700000001_ch0000_button",
        "ABB700000001_ch0001_button",
        "ABB700000001_parameters",
    ]
    sensor_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, "ABB700000001_parameters"
    )
    assert set(hass.states.get(sensor_id).attributes["channel_parameters"]) == {
        "ch0000",
        "ch0001",
    }

    # Channels extended while pending are subscribed once the sensor is added.
    second.update_parameter("par0002", "5")
    await hass.async_block_till_done()
    assert hass.states.get(sensor_id).attributes["channel_parameters"]["ch0001"][
        "parameters"
    ] == {"PID_LED_NIGHT_BRIGHTNESS": "5"}

    # Removing an unrelated device keeps the tracked entities.
    _devices_changed(
        loaded_free_at_home,
        DevicesChangedEvent(removed_device_serials=("ABB700000002",)),
    )
    await hass.async_block_till_done()
    assert hass.states.get(sensor_id) is not None

    # A removed device's entities are created again when it returns.
    _devices_changed(
        loaded_free_at_home,
        DevicesChangedEvent(
            removed_device_serials=("ABB700000001",), added_channels=(first, second)
        ),
    )
    await hass.async_block_till_done()
    assert hass.states.get(sensor_id) is not None
    assert (
        len(
            er.async_entries_for_config_entry(
                entity_registry, mock_config_entry.entry_id
            )
        )
        == 3
    )


async def test_runtime_channel_extends_parameter_sensor(
    hass: HomeAssistant,
    mock_config_entry,
    mock_free_at_home_settings,
    lifecycle_platforms,
) -> None:
    """Test a channel placed later is added to the existing parameter sensor."""
    device = _device()
    first = _trigger(device, "ch0000", parameters={"par0001": "0"})

    mock_fah = await _setup_with_channels(
        hass, mock_config_entry, mock_free_at_home_settings, [first]
    )
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, "ABB700000001_parameters"
    )
    assert set(hass.states.get(entity_id).attributes["channel_parameters"]) == {
        "ch0000"
    }

    second = _trigger(device, "ch0001", parameters={"par0002": "1"})
    mock_fah.channels.append(second)
    _devices_changed(mock_fah, DevicesChangedEvent(added_channels=(second,)))
    await hass.async_block_till_done()

    assert set(hass.states.get(entity_id).attributes["channel_parameters"]) == {
        "ch0000",
        "ch0001",
    }


async def test_unload_removes_devices_changed_callback(
    hass: HomeAssistant, mock_config_entry, loaded_free_at_home
) -> None:
    """Test unloading the entry removes the lifecycle callback."""
    callback_fn = loaded_free_at_home.register_devices_changed_callback.call_args.args[
        0
    ]

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    loaded_free_at_home.ws_close.assert_called_once()
    loaded_free_at_home.remove_devices_changed_callback.assert_called_once_with(
        callback_fn
    )
