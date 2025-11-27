"""Config flow for ABB-free@home integration."""

from __future__ import annotations

from collections.abc import Mapping
from ipaddress import IPv4Address
import logging
from typing import Any

from abbfreeathome import FreeAtHomeApi
from abbfreeathome.api import (
    ClientConnectionError,
    ForbiddenAuthException,
    FreeAtHomeSettings,
    InvalidCredentialsException,
    InvalidHostException,
)
from aiohttp import ClientSession
import voluptuous as vol

from homeassistant.components import zeroconf
from homeassistant.config_entries import (
    CONN_CLASS_LOCAL_PUSH,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_CREATE_SUBDEVICES,
    CONF_INCLUDE_ORPHAN_CHANNELS,
    CONF_INCLUDE_VIRTUAL_DEVICES,
    CONF_SERIAL,
    CONF_SSL_CERT_FILE_PATH,
    CONF_VERIFY_SSL,
    DOMAIN,
    SYSAP_VERSION,
)

_LOGGER = logging.getLogger(__name__)


def _schema_ssl_cert_fields() -> dict:
    """Get SSL configuration fields schema."""
    return {
        vol.Optional(CONF_VERIFY_SSL, description={"suggested_value": True}): bool,
        vol.Optional(CONF_SSL_CERT_FILE_PATH): str,
    }


def _schema_with_defaults(include_ssl: bool = True) -> vol.Schema:
    """Get schema with configurable field inclusion."""
    schema_fields = {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME, default="installer"): str,
        vol.Required(CONF_PASSWORD): str,
    }

    # Add SSL field if requested
    if include_ssl:
        schema_fields.update(_schema_ssl_cert_fields())

    # Add the remaining optional fields
    schema_fields.update(
        {
            vol.Optional(
                CONF_INCLUDE_ORPHAN_CHANNELS, description={"suggested_value": False}
            ): bool,
            vol.Optional(
                CONF_INCLUDE_VIRTUAL_DEVICES, description={"suggested_value": False}
            ): bool,
            vol.Optional(
                CONF_CREATE_SUBDEVICES, description={"suggested_value": False}
            ): bool,
        }
    )

    return vol.Schema(schema_fields)


def _schema_ssl_config() -> vol.Schema:
    """Get schema for SSL configuration step."""
    return vol.Schema(_schema_ssl_cert_fields())


async def validate_settings(
    host: str,
    client_session: ClientSession,
    ssl_cert_file_path: str | None = None,
    verify_ssl: bool = True,
) -> tuple[FreeAtHomeSettings, dict[str, Any]]:
    """Validate the settings endpoint."""
    errors: dict[str, str] = {}

    # Validate SSL configuration
    if verify_ssl and not ssl_cert_file_path:
        errors["ssl_cert_file_path"] = "ssl_cert_required_when_verify_enabled"
        return None, errors

    settings: FreeAtHomeSettings = FreeAtHomeSettings(
        host=host,
        client_session=client_session,
        verify_ssl=verify_ssl,
        ssl_cert_ca_file=ssl_cert_file_path,
    )

    try:
        await settings.load()

        if not settings.has_api_support:
            errors["base"] = "unsupported_sysap_version"
    except InvalidHostException:
        errors["base"] = "cannot_connect"
    except ClientConnectionError:
        errors["base"] = "cannot_connect"
        _LOGGER.exception("Client Connection Error")
    except FileNotFoundError:
        errors["ssl_cert_file_path"] = "ssl_invalid_cert_path"
        _LOGGER.exception("%s - Invalid path for certificate", ssl_cert_file_path)

    return settings, errors


async def validate_api(
    host: str,
    username: str,
    password: str,
    client_session: ClientSession,
    ssl_cert_file_path: str | None = None,
    verify_ssl: bool = True,
) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    errors: dict[str, str] = {}

    # Validate SSL configuration
    if verify_ssl and not ssl_cert_file_path:
        errors["ssl_cert_file_path"] = "ssl_cert_required_when_verify_enabled"
        return errors

    api = FreeAtHomeApi(
        host=host,
        username=username,
        password=password,
        client_session=client_session,
        verify_ssl=verify_ssl,
        ssl_cert_ca_file=ssl_cert_file_path,
    )

    try:
        await api.get_sysap()
    except InvalidCredentialsException:
        errors["base"] = "invalid_auth"
    except ForbiddenAuthException:
        errors["base"] = "invalid_auth"
    except InvalidHostException:
        errors["base"] = "cannot_connect"
    except ClientConnectionError:
        errors["base"] = "cannot_connect"
        _LOGGER.exception("Client Connection Error")
    except FileNotFoundError:
        errors["ssl_cert_file_path"] = "ssl_invalid_cert_path"
        _LOGGER.exception("%s - Invalid path for certificate", ssl_cert_file_path)
    except Exception:
        _LOGGER.exception("Unexpected exception")
        errors["base"] = "unknown"

    return errors


class FreeAtHomeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ABB-free@home."""

    VERSION = 1
    MINOR_VERSION = 5
    CONNECTION_CLASS = CONN_CLASS_LOCAL_PUSH

    def __init__(self) -> None:
        """Initialize."""
        self._host: str | None = None
        self._name: str | None = None
        self._password: str | None = None
        self._serial_number: str | None = None
        self._sysap_version: str | None = None
        self._title: str | None = None
        self._username: str | None = None
        self._include_orphan_channels: bool = False
        self._include_virtual_devices: bool = False
        self._create_subdevices: bool = False
        self._ssl_cert_file_path: str | None = None
        self._verify_ssl: bool = True

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle import from yaml configuration."""
        _default_verify_ssl = self._is_https_host(import_data.get(CONF_HOST))

        # Check/Get Settings
        settings, settings_errors = await validate_settings(
            host=import_data.get(CONF_HOST),
            ssl_cert_file_path=import_data.get(CONF_SSL_CERT_FILE_PATH),
            verify_ssl=import_data.get(CONF_VERIFY_SSL, _default_verify_ssl),
            client_session=async_get_clientsession(self.hass),
        )

        if settings_errors:
            _LOGGER.error(
                "Could not fetch ABB-free@home settings from SysAp; %s",
                settings_errors,
            )
            return self.async_abort(reason="invalid_settings")

        # Check API
        api_errors = await validate_api(
            host=import_data.get(CONF_HOST),
            username=import_data.get(CONF_USERNAME),
            password=import_data.get(CONF_PASSWORD),
            ssl_cert_file_path=import_data.get(CONF_SSL_CERT_FILE_PATH),
            verify_ssl=import_data.get(CONF_VERIFY_SSL, _default_verify_ssl),
            client_session=async_get_clientsession(self.hass),
        )

        if api_errors:
            _LOGGER.error(
                "Could not fetch ABB-free@home api configuration from SysAp; %s",
                api_errors,
            )
            return self.async_abort(reason="invalid_api")

        # Set all required variables for registration
        self._serial_number = settings.serial_number
        self._name = settings.name
        self._title = f"{settings.name} ({settings.serial_number})"
        self._host = import_data.get(CONF_HOST)
        self._username = import_data.get(CONF_USERNAME)
        self._password = import_data.get(CONF_PASSWORD)
        self._include_orphan_channels = import_data.get(CONF_INCLUDE_ORPHAN_CHANNELS)
        self._include_virtual_devices = import_data.get(CONF_INCLUDE_VIRTUAL_DEVICES)
        self._create_subdevices = import_data.get(CONF_CREATE_SUBDEVICES)
        self._ssl_cert_file_path = import_data.get(CONF_SSL_CERT_FILE_PATH)
        self._verify_ssl = import_data.get(CONF_VERIFY_SSL, _default_verify_ssl)

        # If SysAP already exists, update configuration and abort.
        await self.async_set_unique_id(settings.serial_number)
        self._abort_if_unique_id_configured(
            updates={
                CONF_HOST: self._host,
                CONF_USERNAME: self._username,
                CONF_PASSWORD: self._password,
                CONF_INCLUDE_ORPHAN_CHANNELS: self._include_orphan_channels,
                CONF_INCLUDE_VIRTUAL_DEVICES: self._include_virtual_devices,
                CONF_CREATE_SUBDEVICES: self._create_subdevices,
                CONF_SSL_CERT_FILE_PATH: self._ssl_cert_file_path,
                CONF_VERIFY_SSL: self._verify_ssl,
            }
        )

        # Create new config entry.
        return self._async_create_entry()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial user step (basic connection info)."""
        if user_input is None:
            return self._async_show_setup_form(step_id="user")

        # Store the basic connection info
        self._host = user_input.get(CONF_HOST)
        self._username = user_input.get(CONF_USERNAME)
        self._password = user_input.get(CONF_PASSWORD)
        self._include_orphan_channels = user_input.get(CONF_INCLUDE_ORPHAN_CHANNELS)
        self._include_virtual_devices = user_input.get(CONF_INCLUDE_VIRTUAL_DEVICES)
        self._create_subdevices = user_input.get(CONF_CREATE_SUBDEVICES)

        # If it's HTTPS, we need to proceed to SSL config step
        if self._is_https_host(self._host):
            return await self.async_step_ssl_config()

        # Do not verify SSL settings as host is not https
        self._verify_ssl = False

        # For HTTP hosts, validate immediately
        settings, settings_errors = await validate_settings(
            host=self._host,
            verify_ssl=self._verify_ssl,
            client_session=async_get_clientsession(self.hass),
        )
        if settings_errors:
            return self._async_show_setup_form(step_id="user", errors=settings_errors)

        # Check for API Errors
        api_errors = await validate_api(
            host=self._host,
            username=self._username,
            password=self._password,
            verify_ssl=self._verify_ssl,
            client_session=async_get_clientsession(self.hass),
        )
        if api_errors:
            return self._async_show_setup_form(step_id="user", errors=api_errors)

        await self.async_set_unique_id(settings.serial_number)
        self._abort_if_unique_id_configured()

        self._sysap_version = settings.version
        self._serial_number = settings.serial_number
        self._name = settings.name
        self._title = f"{settings.name} ({settings.serial_number})"

        return self._async_create_entry()

    async def async_step_ssl_config(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle SSL configuration step for HTTPS hosts."""
        if user_input is None:
            return self._async_show_setup_form(step_id="ssl_config")

        # Store SSL configuration
        self._ssl_cert_file_path = user_input.get(CONF_SSL_CERT_FILE_PATH)
        self._verify_ssl = user_input.get(CONF_VERIFY_SSL)

        # Now validate with SSL settings
        settings, settings_errors = await validate_settings(
            host=self._host,
            ssl_cert_file_path=self._ssl_cert_file_path,
            verify_ssl=self._verify_ssl,
            client_session=async_get_clientsession(self.hass),
        )
        if settings_errors:
            return self._async_show_setup_form(
                step_id="ssl_config", errors=settings_errors
            )

        # Check for API Errors
        api_errors = await validate_api(
            host=self._host,
            username=self._username,
            password=self._password,
            ssl_cert_file_path=self._ssl_cert_file_path,
            verify_ssl=self._verify_ssl,
            client_session=async_get_clientsession(self.hass),
        )
        if api_errors:
            return self._async_show_setup_form(step_id="ssl_config", errors=api_errors)

        await self.async_set_unique_id(settings.serial_number)
        self._abort_if_unique_id_configured()

        self._sysap_version = settings.version
        self._serial_number = settings.serial_number
        self._name = settings.name
        self._title = f"{settings.name} ({settings.serial_number})"

        return self._async_create_entry()

    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle zeroconf discovery."""
        if not isinstance(discovery_info.ip_address, IPv4Address):
            return self.async_abort(reason="not_ipv4address")

        _sysap_host = f"http://{discovery_info.ip_address.exploded}"
        settings, errors = await validate_settings(
            host=_sysap_host,
            verify_ssl=False,
            client_session=async_get_clientsession(self.hass),
        )
        if errors:
            return self.async_abort(reason="invalid_settings")

        # Preserve existing protocol (http/https) when updating host
        if existing_entry := next(
            (
                entry
                for entry in self._async_current_entries()
                if entry.unique_id == settings.serial_number
            ),
            None,
        ):
            existing_host: str = existing_entry.data.get(CONF_HOST, "")
            if existing_host.startswith("https://"):
                _sysap_host = f"https://{discovery_info.ip_address.exploded}"

        # Check if integration has already been setup.
        await self.async_set_unique_id(settings.serial_number)
        self._abort_if_unique_id_configured(updates={CONF_HOST: _sysap_host})

        # This is a new entry, set class level variables and show setup form.
        self._host = _sysap_host
        self._serial_number = settings.serial_number
        self._name = settings.name
        self._title = f"{settings.name} ({settings.serial_number})"
        self.context["title_placeholders"] = {CONF_NAME: self._title}

        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by zeroconf."""
        if user_input is None:
            return self._async_show_setup_form(
                step_id="zeroconf_confirm", suggested_values={CONF_HOST: self._host}
            )

        self._host = user_input.get(CONF_HOST)
        self._username = user_input.get(CONF_USERNAME)
        self._password = user_input.get(CONF_PASSWORD)
        self._include_orphan_channels = user_input.get(CONF_INCLUDE_ORPHAN_CHANNELS)
        self._include_virtual_devices = user_input.get(CONF_INCLUDE_VIRTUAL_DEVICES)
        self._create_subdevices = user_input.get(CONF_CREATE_SUBDEVICES)

        # If it's HTTPS, we need to proceed to SSL config step
        if self._is_https_host(self._host):
            return await self.async_step_ssl_config()

        # Verify SSL settings as host is not https
        self._verify_ssl = False

        # Check/Get Settings with potentially updated host
        settings, settings_errors = await validate_settings(
            host=self._host,
            verify_ssl=self._verify_ssl,
            client_session=async_get_clientsession(self.hass),
        )
        if settings_errors:
            return self._async_show_setup_form(
                step_id="zeroconf_confirm",
                errors=settings_errors,
                suggested_values={CONF_HOST: self._host},
            )

        errors = await validate_api(
            host=self._host,
            username=self._username,
            password=self._password,
            verify_ssl=self._verify_ssl,
            client_session=async_get_clientsession(self.hass),
        )

        if errors:
            return self._async_show_setup_form(
                step_id="zeroconf_confirm",
                errors=errors,
                suggested_values={CONF_HOST: self._host},
            )

        return self._async_create_entry()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user initiated reconfigure flow."""
        try:
            entry = self._get_reconfigure_entry()
        except AttributeError:  # pragma: no cover
            return self.async_abort(
                reason="reconfigure_not_supported"
            )  # pragma: no cover

        self._host = entry.data.get(CONF_HOST)
        self._name = entry.data.get(CONF_NAME)
        self._serial_number = entry.data.get(CONF_SERIAL)

        if user_input is None:
            return self._async_show_setup_form(
                step_id="reconfigure", suggested_values=entry.data
            )

        # Check/Get Settings with new host
        settings, settings_errors = await validate_settings(
            host=user_input[CONF_HOST],
            ssl_cert_file_path=user_input.get(CONF_SSL_CERT_FILE_PATH),
            verify_ssl=user_input.get(CONF_VERIFY_SSL),
            client_session=async_get_clientsession(self.hass),
        )
        if settings_errors:
            return self._async_show_setup_form(
                step_id="reconfigure",
                errors=settings_errors,
                suggested_values=user_input,
            )

        errors = await validate_api(
            host=user_input[CONF_HOST],
            username=user_input[CONF_USERNAME],
            password=user_input[CONF_PASSWORD],
            ssl_cert_file_path=user_input.get(CONF_SSL_CERT_FILE_PATH),
            verify_ssl=user_input.get(CONF_VERIFY_SSL),
            client_session=async_get_clientsession(self.hass),
        )

        if errors:
            return self._async_show_setup_form(
                step_id="reconfigure",
                errors=errors,
                suggested_values=user_input,
            )

        self._host = user_input[CONF_HOST]
        self._username = user_input[CONF_USERNAME]
        self._password = user_input[CONF_PASSWORD]
        self._include_orphan_channels = user_input[CONF_INCLUDE_ORPHAN_CHANNELS]
        self._include_virtual_devices = user_input[CONF_INCLUDE_VIRTUAL_DEVICES]
        self._create_subdevices = user_input[CONF_CREATE_SUBDEVICES]
        self._ssl_cert_file_path = user_input.get(CONF_SSL_CERT_FILE_PATH)
        self._verify_ssl = user_input.get(CONF_VERIFY_SSL)

        return self._async_update_reload_and_abort()

    @callback
    def _async_create_entry(self) -> ConfigFlowResult:
        return self.async_create_entry(
            title=self._title,
            data={
                CONF_SERIAL: self._serial_number,
                CONF_NAME: self._name,
                CONF_HOST: self._host,
                CONF_USERNAME: self._username,
                CONF_PASSWORD: self._password,
                CONF_INCLUDE_ORPHAN_CHANNELS: self._include_orphan_channels,
                CONF_INCLUDE_VIRTUAL_DEVICES: self._include_virtual_devices,
                CONF_CREATE_SUBDEVICES: self._create_subdevices,
                CONF_SSL_CERT_FILE_PATH: self._ssl_cert_file_path,
                CONF_VERIFY_SSL: self._verify_ssl,
            },
        )

    @callback
    def _async_show_setup_form(
        self,
        step_id: str,
        errors: dict[str, str] | None = None,
        suggested_values: Mapping[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show the setup form."""
        description_placeholders: dict[str, str | None] = {}

        if self._host:
            description_placeholders[CONF_HOST] = self._host
        if self._serial_number:
            description_placeholders[CONF_SERIAL] = self._serial_number
        if self._name:
            description_placeholders[CONF_NAME] = self._name
        if self._sysap_version:
            description_placeholders[SYSAP_VERSION] = self._sysap_version

        if step_id == "ssl_config":
            _schema = _schema_ssl_config()
        else:
            _schema = _schema_with_defaults(include_ssl=step_id != "user")

        # Update suggested value if provided
        if suggested_values:
            _schema = self.add_suggested_values_to_schema(_schema, suggested_values)

        return self.async_show_form(
            step_id=step_id,
            data_schema=_schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )

    @callback
    def _async_update_reload_and_abort(self) -> ConfigFlowResult:
        return self.async_update_reload_and_abort(
            self._get_reconfigure_entry(),
            data_updates={
                CONF_HOST: self._host,
                CONF_USERNAME: self._username,
                CONF_PASSWORD: self._password,
                CONF_INCLUDE_ORPHAN_CHANNELS: self._include_orphan_channels,
                CONF_INCLUDE_VIRTUAL_DEVICES: self._include_virtual_devices,
                CONF_CREATE_SUBDEVICES: self._create_subdevices,
                CONF_SSL_CERT_FILE_PATH: self._ssl_cert_file_path,
                CONF_VERIFY_SSL: self._verify_ssl,
            },
        )

    def _is_https_host(self, host: str) -> bool:
        return host.lower().startswith("https://")
