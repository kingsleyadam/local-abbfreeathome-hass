"""Test the ABB-free@home integration initialization."""

from unittest.mock import AsyncMock, MagicMock, patch

from abbfreeathome.exceptions import BadRequestException
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    CONF_INCLUDE_ORPHAN_CHANNELS,
    CONF_INCLUDE_VIRTUAL_DEVICES,
    CONF_SERIAL,
    CONF_SSL_CERT_FILE_PATH,
    CONF_VERIFY_SSL,
    DOMAIN,
    VIRTUAL_DEVICE,
)
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceValidationError


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
    mock.ws_listen = MagicMock(side_effect=lambda: ws_listen_coro())
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
    assert entry.minor_version == 5
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
    assert entry.minor_version == 5
    assert entry.data[CONF_INCLUDE_VIRTUAL_DEVICES] is False
    assert entry.data[CONF_CREATE_SUBDEVICES] is False
    assert entry.data[CONF_SSL_CERT_FILE_PATH] is None
    assert entry.data[CONF_VERIFY_SSL] is False


async def test_async_migrate_entry_from_v1_4(hass: HomeAssistant) -> None:
    """Test migration from version 1.4."""
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
    assert entry.minor_version == 5
    assert entry.data[CONF_SSL_CERT_FILE_PATH] is None
    assert entry.data[CONF_VERIFY_SSL] is False


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
        minor_version=5,
        domain=DOMAIN,
        title="Test",
        data={
            CONF_HOST: "http://192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password",
            CONF_INCLUDE_ORPHAN_CHANNELS: True,
            CONF_INCLUDE_VIRTUAL_DEVICES: False,
            CONF_CREATE_SUBDEVICES: False,
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
    assert entry.minor_version == 5


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
    assert entry.minor_version == 5
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
    await async_setup_service(hass, entry)

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


async def test_virtual_device_service_minimal_data(hass: HomeAssistant) -> None:
    """Test virtual_device service with minimal data (no optional fields)."""
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
    await async_setup_service(hass, entry)

    # Test service call with only required fields
    result = await hass.services.async_call(
        DOMAIN,
        "virtual_device",
        {
            "serial": "DEVICE456",
            "type": "switch",
            "ttl": 600,
        },
        blocking=True,
        return_response=True,
    )

    assert result == {"status": "ok"}

    # Verify the call was made with correct structure
    call_args = mock_fah.api.virtualdevice.call_args
    assert call_args[1]["serial"] == "DEVICE456"
    assert call_args[1]["data"]["type"] == "switch"
    assert call_args[1]["data"]["properties"]["ttl"] == 600
    # Optional fields should not be in data
    assert "displayname" not in call_args[1]["data"]["properties"]
    assert "flavor" not in call_args[1]["data"]["properties"]
    assert "capabilities" not in call_args[1]["data"]["properties"]


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
    assert entry.minor_version == 5
    # v1.1 -> v1.2 adds orphan channels
    assert entry.data[CONF_INCLUDE_ORPHAN_CHANNELS] is True
    # Then continues to v1.3, v1.4, v1.5
    assert entry.data[CONF_INCLUDE_VIRTUAL_DEVICES] is False
    assert entry.data[CONF_CREATE_SUBDEVICES] is False
    assert entry.data[CONF_SSL_CERT_FILE_PATH] is None
    assert entry.data[CONF_VERIFY_SSL] is False


async def test_async_migrate_entry_from_v1_3(hass: HomeAssistant) -> None:
    """Test migration from version 1.3 through remaining versions to 1.5."""
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
            CONF_INCLUDE_VIRTUAL_DEVICES: False,
        },
        source="user",
        unique_id="TEST123",
    )
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.version == 1
    assert entry.minor_version == 5
    # v1.3 -> v1.4 adds create_subdevices
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
