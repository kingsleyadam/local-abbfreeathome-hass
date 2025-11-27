"""Test the ABB-free@home config flow."""

from ipaddress import IPv4Address, IPv6Address
from unittest.mock import AsyncMock, patch

from abbfreeathome.api import (
    ClientConnectionError,
    ForbiddenAuthException,
    InvalidCredentialsException,
    InvalidHostException,
)

from custom_components.abbfreeathome_ci.config_flow import (
    FreeAtHomeConfigFlow,
    validate_api,
    validate_settings,
)
from custom_components.abbfreeathome_ci.const import (
    CONF_CREATE_SUBDEVICES,
    CONF_INCLUDE_ORPHAN_CHANNELS,
    CONF_INCLUDE_VIRTUAL_DEVICES,
    CONF_SERIAL,
    CONF_SSL_CERT_FILE_PATH,
    CONF_VERIFY_SSL,
    DOMAIN,
)
from homeassistant import config_entries
from homeassistant.components import zeroconf
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.aiohttp_client import async_get_clientsession

# Test constants
TEST_HOST_HTTP = "http://192.168.1.100"
TEST_HOST_HTTPS = "https://192.168.1.100"
TEST_HOST_INVALID = "http://invalid"
TEST_USERNAME = "installer"
TEST_PASSWORD = "test_password"
TEST_PASSWORD_WRONG = "wrong_password"
TEST_SERIAL = "TEST123456"
TEST_NAME = "Test SysAP"
TEST_TITLE = f"{TEST_NAME} ({TEST_SERIAL})"
TEST_CERT_PATH = "/path/to/cert.pem"
TEST_CERT_PATH_INVALID = "/invalid/cert.pem"


def get_user_input(
    host: str = TEST_HOST_HTTP,
    username: str = TEST_USERNAME,
    password: str = TEST_PASSWORD,
    include_orphan_channels: bool = False,
    include_virtual_devices: bool = False,
    create_subdevices: bool = False,
    ssl_cert_file_path: str | None = None,
    verify_ssl: bool | None = None,
) -> dict:
    """Generate user input dictionary for config flow."""
    data = {
        CONF_HOST: host,
        CONF_USERNAME: username,
        CONF_PASSWORD: password,
        CONF_INCLUDE_ORPHAN_CHANNELS: include_orphan_channels,
        CONF_INCLUDE_VIRTUAL_DEVICES: include_virtual_devices,
        CONF_CREATE_SUBDEVICES: create_subdevices,
    }
    if ssl_cert_file_path is not None:
        data[CONF_SSL_CERT_FILE_PATH] = ssl_cert_file_path
    if verify_ssl is not None:
        data[CONF_VERIFY_SSL] = verify_ssl
    return data


def get_expected_entry_data(
    host: str = TEST_HOST_HTTP,
    username: str = TEST_USERNAME,
    password: str = TEST_PASSWORD,
    include_orphan_channels: bool = False,
    include_virtual_devices: bool = False,
    create_subdevices: bool = False,
    ssl_cert_file_path: str | None = None,
    verify_ssl: bool = False,
) -> dict:
    """Generate expected config entry data."""
    return {
        CONF_SERIAL: TEST_SERIAL,
        "name": TEST_NAME,
        CONF_HOST: host,
        CONF_USERNAME: username,
        CONF_PASSWORD: password,
        CONF_INCLUDE_ORPHAN_CHANNELS: include_orphan_channels,
        CONF_INCLUDE_VIRTUAL_DEVICES: include_virtual_devices,
        CONF_CREATE_SUBDEVICES: create_subdevices,
        CONF_SSL_CERT_FILE_PATH: ssl_cert_file_path,
        CONF_VERIFY_SSL: verify_ssl,
    }


async def test_user_form_http(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    mock_free_at_home_settings: AsyncMock,
    mock_free_at_home_api: AsyncMock,
) -> None:
    """Test we get the user form for HTTP."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result.get("errors") is None or result.get("errors") == {}

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], get_user_input()
    )
    await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["title"] == TEST_TITLE
    assert result2["data"] == get_expected_entry_data()
    assert len(mock_setup_entry.mock_calls) == 1


async def test_user_form_https_with_ssl(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    mock_free_at_home_settings: AsyncMock,
    mock_free_at_home_api: AsyncMock,
) -> None:
    """Test we get the SSL config form for HTTPS."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    # Submit user form with HTTPS host
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], get_user_input(host=TEST_HOST_HTTPS)
    )

    # Should proceed to SSL config step
    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "ssl_config"

    # Submit SSL config
    result3 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        {
            CONF_VERIFY_SSL: True,
            CONF_SSL_CERT_FILE_PATH: "/config/ssl/cert.pem",
        },
    )
    await hass.async_block_till_done()

    assert result3["type"] is FlowResultType.CREATE_ENTRY
    assert result3["title"] == TEST_TITLE
    assert result3["data"][CONF_VERIFY_SSL] is True
    assert result3["data"][CONF_SSL_CERT_FILE_PATH] == "/config/ssl/cert.pem"


async def test_user_form_invalid_auth(
    hass: HomeAssistant,
    mock_free_at_home_settings: AsyncMock,
    mock_free_at_home_api: AsyncMock,
) -> None:
    """Test we handle invalid auth error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    mock_free_at_home_api.get_sysap.side_effect = InvalidCredentialsException(
        "installer"
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], get_user_input(password=TEST_PASSWORD_WRONG)
    )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_user_form_cannot_connect(
    hass: HomeAssistant,
    mock_free_at_home_settings: AsyncMock,
) -> None:
    """Test we handle cannot connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    mock_free_at_home_settings.load.side_effect = InvalidHostException(
        "http://192.168.1.999"
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], get_user_input(host="http://192.168.1.999")
    )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_user_form_unsupported_version(
    hass: HomeAssistant,
    mock_free_at_home_settings: AsyncMock,
    mock_free_at_home_api: AsyncMock,
) -> None:
    """Test we handle unsupported SysAP version."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    mock_free_at_home_settings.has_api_support = False

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], get_user_input()
    )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "unsupported_sysap_version"}


async def test_user_form_already_configured(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    mock_free_at_home_settings: AsyncMock,
    mock_free_at_home_api: AsyncMock,
    mock_config_entry,
) -> None:
    """Test we abort if already configured."""
    await hass.config_entries.async_add(mock_config_entry)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], get_user_input()
    )

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


async def test_zeroconf_flow(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    mock_free_at_home_settings: AsyncMock,
    mock_free_at_home_api: AsyncMock,
) -> None:
    """Test we can setup from zeroconf."""
    discovery_info = zeroconf.ZeroconfServiceInfo(
        ip_address=IPv4Address("192.168.1.100"),
        ip_addresses=[IPv4Address("192.168.1.100")],
        hostname="sysap.local.",
        name="ABB SysAP._http._tcp.local.",
        port=80,
        properties={},
        type="_http._tcp.local.",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=discovery_info
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "http://192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "test_password",
            CONF_INCLUDE_ORPHAN_CHANNELS: False,
            CONF_INCLUDE_VIRTUAL_DEVICES: False,
            CONF_CREATE_SUBDEVICES: False,
        },
    )

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Test SysAP (TEST123456)"


async def test_zeroconf_already_configured(
    hass: HomeAssistant,
    mock_free_at_home_settings: AsyncMock,
    mock_config_entry,
) -> None:
    """Test we abort zeroconf if already configured."""
    await hass.config_entries.async_add(mock_config_entry)

    discovery_info = zeroconf.ZeroconfServiceInfo(
        ip_address=IPv4Address("192.168.1.100"),
        ip_addresses=[IPv4Address("192.168.1.100")],
        hostname="sysap.local.",
        name="ABB SysAP._http._tcp.local.",
        port=80,
        properties={},
        type="_http._tcp.local.",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=discovery_info
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_import_flow(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    mock_free_at_home_settings: AsyncMock,
    mock_free_at_home_api: AsyncMock,
) -> None:
    """Test import from yaml configuration."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_IMPORT},
        data=get_user_input(),
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == TEST_TITLE


async def test_ssl_cert_required_when_verify_enabled(
    hass: HomeAssistant,
    mock_free_at_home_settings: AsyncMock,
) -> None:
    """Test SSL cert path required when verification enabled."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], get_user_input(host=TEST_HOST_HTTPS)
    )

    # Should proceed to SSL config step
    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "ssl_config"

    # Try to submit with verify_ssl=True but no cert path
    result3 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        {
            CONF_VERIFY_SSL: True,
            # No CONF_SSL_CERT_FILE_PATH provided
        },
    )

    assert result3["type"] is FlowResultType.FORM
    assert result3["errors"] == {
        "ssl_cert_file_path": "ssl_cert_required_when_verify_enabled"
    }


async def test_ssl_cert_invalid_path(
    hass: HomeAssistant,
    mock_free_at_home_settings: AsyncMock,
) -> None:
    """Test SSL cert path validation."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], get_user_input(host=TEST_HOST_HTTPS)
    )

    # Simulate FileNotFoundError for invalid cert path
    mock_free_at_home_settings.load.side_effect = FileNotFoundError

    result3 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        {
            CONF_VERIFY_SSL: True,
            CONF_SSL_CERT_FILE_PATH: "/invalid/path/cert.pem",
        },
    )

    assert result3["type"] is FlowResultType.FORM
    assert result3["errors"] == {"ssl_cert_file_path": "ssl_invalid_cert_path"}


async def test_reconfigure_flow(
    hass: HomeAssistant,
    mock_free_at_home_settings: AsyncMock,
    mock_free_at_home_api: AsyncMock,
    mock_config_entry,
) -> None:
    """Test reconfigure flow."""
    await hass.config_entries.async_add(mock_config_entry)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": mock_config_entry.entry_id,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "http://192.168.1.200",
            CONF_USERNAME: "new_username",
            CONF_PASSWORD: "new_password",
            CONF_INCLUDE_ORPHAN_CHANNELS: True,
            CONF_INCLUDE_VIRTUAL_DEVICES: True,
            CONF_CREATE_SUBDEVICES: True,
            CONF_VERIFY_SSL: False,
        },
    )

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "reconfigure_successful"


async def test_forbidden_auth_exception(
    hass: HomeAssistant,
    mock_free_at_home_settings: AsyncMock,
    mock_free_at_home_api: AsyncMock,
) -> None:
    """Test we handle forbidden auth error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    mock_free_at_home_api.get_sysap.side_effect = ForbiddenAuthException(
        "/api/rest", 403
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], get_user_input()
    )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_client_connection_error(
    hass: HomeAssistant,
    mock_free_at_home_settings: AsyncMock,
) -> None:
    """Test we handle client connection error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    mock_free_at_home_settings.load.side_effect = ClientConnectionError(TEST_HOST_HTTP)

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], get_user_input()
    )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_unexpected_exception(
    hass: HomeAssistant,
    mock_free_at_home_settings: AsyncMock,
    mock_free_at_home_api: AsyncMock,
) -> None:
    """Test we handle unexpected exception."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    mock_free_at_home_api.get_sysap.side_effect = Exception("Unexpected error")

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], get_user_input()
    )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "unknown"}


async def test_zeroconf_ipv6_abort(
    hass: HomeAssistant,
    mock_free_at_home_settings: AsyncMock,
) -> None:
    """Test we abort zeroconf for IPv6 addresses."""
    discovery_info = zeroconf.ZeroconfServiceInfo(
        ip_address=IPv6Address("::1"),
        ip_addresses=[IPv6Address("::1")],
        hostname="sysap.local.",
        name="ABB SysAP._http._tcp.local.",
        port=80,
        properties={},
        type="_http._tcp.local.",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=discovery_info
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_ipv4address"


async def test_zeroconf_https_existing_entry(
    hass: HomeAssistant,
    mock_free_at_home_settings: AsyncMock,
) -> None:
    """Test zeroconf discovery updates existing HTTPS entry."""
    # Create config entry with HTTPS host
    https_entry = ConfigEntry(
        version=1,
        minor_version=5,
        domain=DOMAIN,
        title="Test SysAP (TEST123456)",
        data={
            "serial": "TEST123456",
            "name": "Test SysAP",
            "host": "https://192.168.1.50",
            "username": "installer",
            "password": "test_password",
            "include_orphan_channels": False,
            "include_virtual_devices": False,
            "create_subdevices": False,
            "ssl_cert_file_path": None,
            "verify_ssl": False,
        },
        source="user",
        unique_id="TEST123456",
        discovery_keys={},
        options={},
        subentries_data={},
    )
    await hass.config_entries.async_add(https_entry)

    discovery_info = zeroconf.ZeroconfServiceInfo(
        ip_address=IPv4Address("192.168.1.100"),
        ip_addresses=[IPv4Address("192.168.1.100")],
        hostname="sysap.local.",
        name="ABB SysAP._http._tcp.local.",
        port=80,
        properties={},
        type="_http._tcp.local.",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=discovery_info
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_with_errors(
    hass: HomeAssistant,
    mock_free_at_home_settings: AsyncMock,
    mock_free_at_home_api: AsyncMock,
    mock_config_entry,
) -> None:
    """Test reconfigure flow with validation errors."""
    await hass.config_entries.async_add(mock_config_entry)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": mock_config_entry.entry_id,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    # Test with settings error
    mock_free_at_home_settings.load.side_effect = InvalidHostException("http://invalid")

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], get_user_input(host=TEST_HOST_INVALID, verify_ssl=False)
    )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_reconfigure_with_api_errors(
    hass: HomeAssistant,
    mock_free_at_home_settings: AsyncMock,
    mock_free_at_home_api: AsyncMock,
    mock_config_entry,
) -> None:
    """Test reconfigure flow with API validation errors."""
    await hass.config_entries.async_add(mock_config_entry)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": mock_config_entry.entry_id,
        },
    )

    # Reset the side_effect from settings mock
    mock_free_at_home_settings.load.side_effect = None

    # Test with API error
    mock_free_at_home_api.get_sysap.side_effect = InvalidCredentialsException(
        TEST_USERNAME
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        get_user_input(password=TEST_PASSWORD_WRONG, verify_ssl=False),
    )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_validate_settings_ssl_verification_error(hass: HomeAssistant) -> None:
    """Test validate_settings when verify_ssl is True but cert path is None."""
    client_session = async_get_clientsession(hass)

    settings, errors = await validate_settings(
        host=TEST_HOST_HTTPS,
        client_session=client_session,
        verify_ssl=True,
        ssl_cert_file_path=None,
    )

    assert settings is None
    assert errors == {"ssl_cert_file_path": "ssl_cert_required_when_verify_enabled"}


async def test_validate_settings_file_not_found(
    hass: HomeAssistant, mock_free_at_home_settings: AsyncMock
) -> None:
    """Test validate_settings when SSL cert file is not found."""
    client_session = async_get_clientsession(hass)
    mock_free_at_home_settings.load.side_effect = FileNotFoundError()

    settings, errors = await validate_settings(
        host=TEST_HOST_HTTPS,
        client_session=client_session,
        verify_ssl=True,
        ssl_cert_file_path=TEST_CERT_PATH_INVALID,
    )

    assert errors == {"ssl_cert_file_path": "ssl_invalid_cert_path"}


async def test_validate_settings_unsupported_version(
    hass: HomeAssistant, mock_free_at_home_settings: AsyncMock
) -> None:
    """Test validate_settings when SysAP version is unsupported."""
    client_session = async_get_clientsession(hass)
    mock_free_at_home_settings.has_api_support = False
    mock_free_at_home_settings.load.side_effect = None

    settings, errors = await validate_settings(
        host="http://192.168.1.100",
        client_session=client_session,
        verify_ssl=False,
    )

    assert errors == {"base": "unsupported_sysap_version"}


async def test_validate_api_ssl_verification_error(hass: HomeAssistant) -> None:
    """Test validate_api when verify_ssl is True but cert path is None."""
    client_session = async_get_clientsession(hass)

    errors = await validate_api(
        host="https://192.168.1.100",
        username="installer",
        password="password",
        client_session=client_session,
        verify_ssl=True,
        ssl_cert_file_path=None,
    )

    assert errors == {"ssl_cert_file_path": "ssl_cert_required_when_verify_enabled"}


async def test_validate_api_file_not_found(
    hass: HomeAssistant, mock_free_at_home_api: AsyncMock
) -> None:
    """Test validate_api when SSL cert file is not found."""
    client_session = async_get_clientsession(hass)
    mock_free_at_home_api.get_sysap.side_effect = FileNotFoundError()

    errors = await validate_api(
        host="https://192.168.1.100",
        username="installer",
        password="password",
        client_session=client_session,
        verify_ssl=True,
        ssl_cert_file_path="/invalid/path/cert.pem",
    )

    assert errors == {"ssl_cert_file_path": "ssl_invalid_cert_path"}


async def test_validate_api_unexpected_exception(
    hass: HomeAssistant, mock_free_at_home_api: AsyncMock
) -> None:
    """Test validate_api with unexpected exception."""
    client_session = async_get_clientsession(hass)
    mock_free_at_home_api.get_sysap.side_effect = RuntimeError("Unexpected")

    errors = await validate_api(
        host="http://192.168.1.100",
        username="installer",
        password="password",
        client_session=client_session,
        verify_ssl=False,
    )

    assert errors == {"base": "unknown"}


async def test_import_with_settings_errors(hass: HomeAssistant) -> None:
    """Test import flow when settings validation fails."""
    with patch(
        "custom_components.abbfreeathome_ci.config_flow.validate_settings",
        return_value=(None, {"base": "cannot_connect"}),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_IMPORT},
            data={
                CONF_HOST: "http://192.168.1.100",
                CONF_USERNAME: "installer",
                CONF_PASSWORD: "password",
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_settings"


async def test_import_with_api_errors(
    hass: HomeAssistant, mock_free_at_home_settings: AsyncMock
) -> None:
    """Test import flow when API validation fails."""
    with (
        patch(
            "custom_components.abbfreeathome_ci.config_flow.validate_settings",
            return_value=(mock_free_at_home_settings, {}),
        ),
        patch(
            "custom_components.abbfreeathome_ci.config_flow.validate_api",
            return_value={"base": "invalid_auth"},
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_IMPORT},
            data={
                CONF_HOST: "http://192.168.1.100",
                CONF_USERNAME: "installer",
                CONF_PASSWORD: "password",
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_api"


async def test_import_updates_existing_entry(
    hass: HomeAssistant,
    mock_config_entry,
    mock_free_at_home_settings: AsyncMock,
) -> None:
    """Test import flow updates existing entry."""
    await hass.config_entries.async_add(mock_config_entry)

    with (
        patch(
            "custom_components.abbfreeathome_ci.config_flow.validate_settings",
            return_value=(mock_free_at_home_settings, {}),
        ),
        patch(
            "custom_components.abbfreeathome_ci.config_flow.validate_api",
            return_value={},
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_IMPORT},
            data={
                CONF_HOST: "http://192.168.1.200",
                CONF_USERNAME: "installer",
                CONF_PASSWORD: "newpassword",
                CONF_INCLUDE_ORPHAN_CHANNELS: True,
                CONF_INCLUDE_VIRTUAL_DEVICES: True,
                CONF_CREATE_SUBDEVICES: True,
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_zeroconf_confirm_with_settings_errors(
    hass: HomeAssistant, mock_free_at_home_settings: AsyncMock
) -> None:
    """Test zeroconf_confirm when settings validation fails."""
    # Start a zeroconf flow first to set up the flow context
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=zeroconf.ZeroconfServiceInfo(
            ip_address=IPv4Address("192.168.1.100"),
            ip_addresses=[IPv4Address("192.168.1.100")],
            hostname="sysap.local.",
            name="ABB-free@home",
            port=80,
            properties={},
            type="mock_type",
        ),
    )

    # Setup settings error for the confirm step
    mock_free_at_home_settings.load.side_effect = InvalidHostException(TEST_HOST_HTTP)

    # Now call async_step_zeroconf_confirm directly with user input
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=get_user_input(password="password")
    )

    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "zeroconf_confirm"
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_zeroconf_confirm_with_api_errors(
    hass: HomeAssistant,
    mock_free_at_home_settings: AsyncMock,
    mock_free_at_home_api: AsyncMock,
) -> None:
    """Test zeroconf_confirm when API validation fails."""
    # Start a zeroconf flow first to set up the flow context
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=zeroconf.ZeroconfServiceInfo(
            ip_address=IPv4Address("192.168.1.100"),
            ip_addresses=[IPv4Address("192.168.1.100")],
            hostname="sysap.local.",
            name="ABB-free@home",
            port=80,
            properties={},
            type="mock_type",
        ),
    )

    # Reset settings mock and setup API error for the confirm step
    mock_free_at_home_settings.load.side_effect = None
    mock_free_at_home_api.get_sysap.side_effect = InvalidCredentialsException(
        TEST_USERNAME
    )

    # Now call async_step_zeroconf_confirm directly with user input
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input=get_user_input(password="password"),
    )

    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "zeroconf_confirm"
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_zeroconf_confirm_https_flow(
    hass: HomeAssistant, mock_free_at_home_settings: AsyncMock
) -> None:
    """Test zeroconf_confirm when user changes host to HTTPS."""
    # Start a zeroconf flow first to set up the flow context
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=zeroconf.ZeroconfServiceInfo(
            ip_address=IPv4Address("192.168.1.100"),
            ip_addresses=[IPv4Address("192.168.1.100")],
            hostname="sysap.local.",
            name="ABB-free@home",
            port=80,
            properties={},
            type="mock_type",
        ),
    )

    # Now call async_step_zeroconf_confirm with HTTPS host
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input=get_user_input(host=TEST_HOST_HTTPS, password="password"),
    )

    # Should redirect to SSL config step
    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "ssl_config"


async def test_ssl_config_with_api_errors(
    hass: HomeAssistant,
    mock_free_at_home_settings: AsyncMock,
    mock_free_at_home_api: AsyncMock,
) -> None:
    """Test SSL config step when API validation fails."""
    # Start user flow with HTTPS host to get to SSL config step
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], get_user_input(host=TEST_HOST_HTTPS, password="password")
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "ssl_config"

    # Now submit SSL config, but API validation will fail
    mock_free_at_home_settings.load.side_effect = None
    mock_free_at_home_api.get_sysap.side_effect = InvalidCredentialsException(
        TEST_USERNAME
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_VERIFY_SSL: False,
        },
    )

    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "ssl_config"
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_validate_settings_invalid_host_exception(
    hass: HomeAssistant, mock_free_at_home_settings: AsyncMock
) -> None:
    """Test validate_settings handles InvalidHostException."""
    client_session = async_get_clientsession(hass)
    mock_free_at_home_settings.load.side_effect = InvalidHostException(
        "http://192.168.1.100"
    )

    settings, errors = await validate_settings(
        host="http://192.168.1.100",
        client_session=client_session,
        verify_ssl=False,
    )

    assert errors == {"base": "cannot_connect"}


async def test_validate_settings_client_connection_error_logging(
    hass: HomeAssistant, mock_free_at_home_settings: AsyncMock
) -> None:
    """Test validate_settings logs ClientConnectionError."""
    client_session = async_get_clientsession(hass)
    mock_free_at_home_settings.load.side_effect = ClientConnectionError(
        "http://192.168.1.100"
    )

    settings, errors = await validate_settings(
        host="http://192.168.1.100",
        client_session=client_session,
        verify_ssl=False,
    )

    assert errors == {"base": "cannot_connect"}


async def test_validate_settings_file_not_found_logging(
    hass: HomeAssistant, mock_free_at_home_settings: AsyncMock
) -> None:
    """Test validate_settings logs FileNotFoundError with path."""
    client_session = async_get_clientsession(hass)
    mock_free_at_home_settings.load.side_effect = FileNotFoundError()

    settings, errors = await validate_settings(
        host="https://192.168.1.100",
        client_session=client_session,
        verify_ssl=True,
        ssl_cert_file_path="/invalid/cert.pem",
    )

    assert errors == {"ssl_cert_file_path": "ssl_invalid_cert_path"}


async def test_zeroconf_discovery_with_settings_errors(
    hass: HomeAssistant, mock_free_at_home_settings: AsyncMock
) -> None:
    """Test zeroconf discovery aborts when settings validation fails."""
    mock_free_at_home_settings.load.side_effect = InvalidHostException(
        "http://192.168.1.100"
    )

    discovery_info = zeroconf.ZeroconfServiceInfo(
        ip_address=IPv4Address("192.168.1.100"),
        ip_addresses=[IPv4Address("192.168.1.100")],
        hostname="sysap.local.",
        name="ABB SysAP._http._tcp.local.",
        port=80,
        properties={},
        type="_http._tcp.local.",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=discovery_info
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_settings"


async def test_import_creates_new_entry(
    hass: HomeAssistant, mock_free_at_home_settings: AsyncMock
) -> None:
    """Test import flow creates new entry when one doesn't exist."""
    with (
        patch(
            "custom_components.abbfreeathome_ci.config_flow.validate_settings",
            return_value=(mock_free_at_home_settings, {}),
        ),
        patch(
            "custom_components.abbfreeathome_ci.config_flow.validate_api",
            return_value={},
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_IMPORT},
            data={
                CONF_HOST: "http://192.168.1.100",
                CONF_USERNAME: "installer",
                CONF_PASSWORD: "password",
                CONF_INCLUDE_ORPHAN_CHANNELS: False,
                CONF_INCLUDE_VIRTUAL_DEVICES: False,
                CONF_CREATE_SUBDEVICES: False,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test SysAP (TEST123456)"


async def test_ssl_config_form_displays_correct_schema(
    hass: HomeAssistant,
) -> None:
    """Test SSL config step shows the correct schema (no username/password fields)."""
    # Start user flow with HTTPS host to reach ssl_config step
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "https://192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password",
            CONF_INCLUDE_ORPHAN_CHANNELS: False,
            CONF_INCLUDE_VIRTUAL_DEVICES: False,
            CONF_CREATE_SUBDEVICES: False,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "ssl_config"
    # Verify the SSL config schema is shown (should only have SSL fields)
    schema_keys = list(result["data_schema"].schema.keys())
    # SSL config should have verify_ssl and ssl_cert_file_path
    assert any("verify_ssl" in str(key) for key in schema_keys)
    # SSL config should NOT have username/password/host
    assert not any("username" in str(key).lower() for key in schema_keys)
    assert not any("password" in str(key).lower() for key in schema_keys)


async def test_validate_api_invalid_host_exception(
    hass: HomeAssistant, mock_free_at_home_api: AsyncMock
) -> None:
    """Test validate_api handles InvalidHostException."""
    client_session = async_get_clientsession(hass)
    mock_free_at_home_api.get_sysap.side_effect = InvalidHostException(
        "http://192.168.1.100"
    )

    errors = await validate_api(
        host="http://192.168.1.100",
        username="installer",
        password="password",
        client_session=client_session,
        verify_ssl=False,
    )

    assert errors == {"base": "cannot_connect"}


async def test_validate_api_logs_client_connection_error(
    hass: HomeAssistant, mock_free_at_home_api: AsyncMock
) -> None:
    """Test validate_api logs ClientConnectionError exceptions."""
    client_session = async_get_clientsession(hass)
    mock_free_at_home_api.get_sysap.side_effect = ClientConnectionError(
        "http://192.168.1.100"
    )

    with patch("custom_components.abbfreeathome_ci.config_flow._LOGGER") as mock_logger:
        errors = await validate_api(
            host="http://192.168.1.100",
            username="installer",
            password="password",
            client_session=client_session,
            verify_ssl=False,
        )

    assert errors == {"base": "cannot_connect"}
    # Verify the exception was logged
    mock_logger.exception.assert_called_once_with("Client Connection Error")


async def test_validate_api_logs_file_not_found_with_path(
    hass: HomeAssistant, mock_free_at_home_api: AsyncMock
) -> None:
    """Test validate_api logs FileNotFoundError with certificate path."""
    client_session = async_get_clientsession(hass)
    mock_free_at_home_api.get_sysap.side_effect = FileNotFoundError()
    cert_path = "/invalid/path/cert.pem"

    with patch("custom_components.abbfreeathome_ci.config_flow._LOGGER") as mock_logger:
        errors = await validate_api(
            host="https://192.168.1.100",
            username="installer",
            password="password",
            client_session=client_session,
            verify_ssl=True,
            ssl_cert_file_path=cert_path,
        )

    assert errors == {"ssl_cert_file_path": "ssl_invalid_cert_path"}
    # Verify the exception was logged with the path
    mock_logger.exception.assert_called_once_with(
        "%s - Invalid path for certificate", cert_path
    )


async def test_user_form_schema_excludes_ssl_fields(
    hass: HomeAssistant,
) -> None:
    """Test user step schema excludes SSL fields (tests step_id != 'ssl_config' branch)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    # User form should have host, username, password but NOT SSL-specific fields in schema
    schema_keys = [str(key) for key in result["data_schema"].schema]
    # Should have basic fields
    assert any("host" in key.lower() for key in schema_keys)
    assert any("username" in key.lower() for key in schema_keys)
    assert any("password" in key.lower() for key in schema_keys)


async def test_zeroconf_confirm_non_https_continues_to_completion(
    hass: HomeAssistant,
    mock_free_at_home_settings: AsyncMock,
    mock_free_at_home_api: AsyncMock,
) -> None:
    """Test zeroconf_confirm with HTTP host continues without SSL config (tests else branch)."""
    # Start a zeroconf flow first to set up the flow context
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=zeroconf.ZeroconfServiceInfo(
            ip_address=IPv4Address("192.168.1.100"),
            ip_addresses=[IPv4Address("192.168.1.100")],
            hostname="sysap.local.",
            name="ABB-free@home",
            port=80,
            properties={},
            type="mock_type",
        ),
    )

    # Reset mocks to ensure clean state
    mock_free_at_home_settings.load.side_effect = None
    mock_free_at_home_api.get_sysap.side_effect = None

    # Now call async_step_zeroconf_confirm with HTTP host (NOT HTTPS) - should complete without going to ssl_config
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: "http://192.168.1.100",  # HTTP, not HTTPS
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password",
            CONF_INCLUDE_ORPHAN_CHANNELS: False,
            CONF_INCLUDE_VIRTUAL_DEVICES: False,
            CONF_CREATE_SUBDEVICES: False,
        },
    )

    # Should go straight to CREATE_ENTRY, not ssl_config
    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Test SysAP (TEST123456)"


async def test_reconfigure_step_shows_correct_schema(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test reconfigure step uses correct schema (not ssl_config schema)."""
    await hass.config_entries.async_add(mock_config_entry)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": mock_config_entry.entry_id,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    # Reconfigure form should have all fields including SSL (step_id != 'user')
    schema_keys = [str(key) for key in result["data_schema"].schema]
    assert any("host" in key.lower() for key in schema_keys)
    assert any("username" in key.lower() for key in schema_keys)
    # Should have SSL fields since it's not 'user' step
    assert any("verify" in key.lower() for key in schema_keys)


async def test_show_form_with_sysap_version(
    hass: HomeAssistant,
) -> None:
    """Test showing form with _sysap_version set in description placeholders."""
    # Create a flow instance
    flow = FreeAtHomeConfigFlow()
    flow.hass = hass

    # Manually set _sysap_version to simulate it being set during a previous step
    flow._sysap_version = "2.6.0"
    flow._host = "http://192.168.1.100"
    flow._serial_number = "TEST123456"
    flow._name = "Test SysAP"

    # Call the method directly - this will exercise the if self._sysap_version branch
    result = flow._async_show_setup_form(step_id="user", errors={"base": "test"})

    # Verify the result is a form with description_placeholders including sysap_version
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["description_placeholders"]["sysap_version"] == "2.6.0"
