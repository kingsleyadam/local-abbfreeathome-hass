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
    CONF_SSL_CERT_PATH,
    DOMAIN,
    SYSAP_VERSION,
)

_LOGGER = logging.getLogger(__name__)


def _schema_with_defaults(
    host: str | None = None,
    username: str | None = None,
    include_orphan_channels: bool = False,
    include_virtual_devices: bool = False,
    create_subdevices: bool = False,
    ssl_cert_path: str | None = None,
    step_id: str = "user",
) -> vol.Schema:
    schema = vol.Schema({})

    if step_id in ["user"]:
        schema = schema.extend({vol.Required(CONF_HOST, default=host): str})

    return schema.extend(
        {
            vol.Required(CONF_USERNAME, default=username or "installer"): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(
                CONF_INCLUDE_ORPHAN_CHANNELS, default=include_orphan_channels
            ): bool,
            vol.Optional(
                CONF_INCLUDE_VIRTUAL_DEVICES, default=include_virtual_devices
            ): bool,
            vol.Optional(CONF_CREATE_SUBDEVICES, default=create_subdevices): bool,
            vol.Optional(
                CONF_SSL_CERT_PATH,
                **({} if ssl_cert_path is None else {"default": ssl_cert_path}),
            ): str,
        }
    )


async def validate_settings(
    host: str, client_session: ClientSession, ssl_cert_path: str | None = None
) -> tuple[FreeAtHomeSettings, dict[str, Any]]:
    """Validate the settings endpoint."""
    errors: dict[str, str] = {}
    verify_ssl = bool(ssl_cert_path)

    settings: FreeAtHomeSettings = FreeAtHomeSettings(
        host=host,
        client_session=client_session,
        verify_ssl=verify_ssl,
        ssl_cert_ca_file=ssl_cert_path,
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

    return settings, errors


async def validate_api(
    host: str,
    username: str,
    password: str,
    client_session: ClientSession,
    ssl_cert_path: str | None = None,
) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    errors: dict[str, str] = {}
    verify_ssl = bool(ssl_cert_path)

    api = FreeAtHomeApi(
        host=host,
        username=username,
        password=password,
        client_session=client_session,
        verify_ssl=verify_ssl,
        ssl_cert_ca_file=ssl_cert_path,
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
        self._ssl_cert_path: str | None = None

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle import from yaml configuration."""
        # Check/Get Settings
        settings, settings_errors = await validate_settings(
            host=import_data[CONF_HOST],
            client_session=async_get_clientsession(self.hass),
            ssl_cert_path=import_data.get(CONF_SSL_CERT_PATH),
        )

        if settings_errors:
            _LOGGER.error(
                "Could not fetch ABB-free@home settings from SysAp; %s",
                settings_errors.get("base"),
            )
            return self.async_abort(reason="invalid_settings")

        # Check API
        api_errors = await validate_api(
            host=import_data[CONF_HOST],
            username=import_data[CONF_USERNAME],
            password=import_data[CONF_PASSWORD],
            client_session=async_get_clientsession(self.hass),
            ssl_cert_path=import_data.get(CONF_SSL_CERT_PATH),
        )

        if api_errors:
            _LOGGER.error(
                "Could not fetch ABB-free@home settings from SysAp; %s",
                api_errors.get("base"),
            )
            return self.async_abort(reason="invalid_api")

        # Set all required variables for registration
        self._serial_number = settings.serial_number
        self._name = settings.name
        self._title = f"{settings.name} ({settings.serial_number})"
        self._host = import_data[CONF_HOST]
        self._username = import_data[CONF_USERNAME]
        self._password = import_data[CONF_PASSWORD]
        self._include_orphan_channels = import_data[CONF_INCLUDE_ORPHAN_CHANNELS]
        self._include_virtual_devices = import_data[CONF_INCLUDE_VIRTUAL_DEVICES]
        self._create_subdevices = import_data[CONF_CREATE_SUBDEVICES]
        self._ssl_cert_path = import_data.get(CONF_SSL_CERT_PATH)

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
                CONF_SSL_CERT_PATH: self._ssl_cert_path,
            }
        )

        # Create new config entry.
        return self._async_create_entry()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial user step."""
        if user_input is None:
            return self._async_show_setup_form(step_id="user")

        # Check/Get Settings
        settings, settings_errors = await validate_settings(
            host=user_input[CONF_HOST],
            client_session=async_get_clientsession(self.hass),
            ssl_cert_path=user_input.get(CONF_SSL_CERT_PATH),
        )
        if settings_errors.get("base") != "cannot_connect":
            self._sysap_version = settings.version
        if settings_errors:
            return self._async_show_setup_form(step_id="user", errors=settings_errors)

        # Check for API Errors
        api_errors = await validate_api(
            host=user_input[CONF_HOST],
            username=user_input[CONF_USERNAME],
            password=user_input[CONF_PASSWORD],
            client_session=async_get_clientsession(self.hass),
            ssl_cert_path=user_input.get(CONF_SSL_CERT_PATH),
        )
        if api_errors:
            return self._async_show_setup_form(step_id="user", errors=api_errors)

        await self.async_set_unique_id(settings.serial_number)
        self._abort_if_unique_id_configured()

        self._serial_number = settings.serial_number
        self._name = settings.name
        self._title = f"{settings.name} ({settings.serial_number})"

        self._host = user_input[CONF_HOST]
        self._username = user_input[CONF_USERNAME]
        self._password = user_input[CONF_PASSWORD]
        self._include_orphan_channels = user_input[CONF_INCLUDE_ORPHAN_CHANNELS]
        self._include_virtual_devices = user_input[CONF_INCLUDE_VIRTUAL_DEVICES]
        self._create_subdevices = user_input[CONF_CREATE_SUBDEVICES]
        self._ssl_cert_path = user_input.get(CONF_SSL_CERT_PATH)

        return self._async_create_entry()

    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle zeroconf discovery."""
        if not isinstance(discovery_info.ip_address, IPv4Address):
            return self.async_abort(reason="not_ipv4address")

        self._host = f"http://{discovery_info.ip_address.exploded}"
        settings, errors = await validate_settings(
            host=self._host,
            client_session=async_get_clientsession(self.hass),
            ssl_cert_path=None,
        )

        if errors:
            return self.async_abort(reason="invalid_settings")

        self._serial_number = settings.serial_number
        self._name = settings.name
        self._title = f"{settings.name} ({settings.serial_number})"

        await self.async_set_unique_id(settings.serial_number)
        self._abort_if_unique_id_configured(updates={CONF_HOST: self._host})
        self.context["title_placeholders"] = {CONF_NAME: self._title}

        return self._async_show_setup_form(
            step_id="zeroconf_confirm",
        )

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by zeroconf."""
        if user_input is None:
            return self._async_show_setup_form(step_id="zeroconf_confirm")

        errors = await validate_api(
            host=self._host,
            username=user_input[CONF_USERNAME],
            password=user_input[CONF_PASSWORD],
            client_session=async_get_clientsession(self.hass),
            ssl_cert_path=user_input.get(CONF_SSL_CERT_PATH),
        )

        if errors:
            return self._async_show_setup_form(
                step_id="zeroconf_confirm", errors=errors
            )

        self._username = user_input[CONF_USERNAME]
        self._password = user_input[CONF_PASSWORD]
        self._include_orphan_channels = user_input[CONF_INCLUDE_ORPHAN_CHANNELS]
        self._include_virtual_devices = user_input[CONF_INCLUDE_VIRTUAL_DEVICES]
        self._create_subdevices = user_input[CONF_CREATE_SUBDEVICES]
        self._ssl_cert_path = user_input.get(CONF_SSL_CERT_PATH)

        return self._async_create_entry()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user initiated reconfigure flow."""
        try:
            entry = self._get_reconfigure_entry()
        except AttributeError:
            return self.async_abort(reason="reconfigure_not_supported")

        self._host = entry.data[CONF_HOST]
        self._name = entry.data[CONF_NAME]
        self._username = entry.data[CONF_USERNAME]
        self._serial_number = entry.data[CONF_SERIAL]
        self._include_orphan_channels = entry.data[CONF_INCLUDE_ORPHAN_CHANNELS]
        self._include_virtual_devices = entry.data[CONF_INCLUDE_VIRTUAL_DEVICES]
        self._create_subdevices = entry.data[CONF_CREATE_SUBDEVICES]
        self._ssl_cert_path = entry.data.get(CONF_SSL_CERT_PATH)

        if user_input is None:
            return self._async_show_setup_form(
                step_id="reconfigure",
                username=self._username,
                include_orphan_channels=self._include_orphan_channels,
                include_virtual_devices=self._include_virtual_devices,
                create_subdevices=self._create_subdevices,
                ssl_cert_path=self._ssl_cert_path,
            )

        errors = await validate_api(
            host=self._host,
            username=user_input[CONF_USERNAME],
            password=user_input[CONF_PASSWORD],
            client_session=async_get_clientsession(self.hass),
            ssl_cert_path=user_input.get(CONF_SSL_CERT_PATH),
        )

        if errors:
            return self._async_show_setup_form(step_id="reconfigure", errors=errors)

        self._username = user_input[CONF_USERNAME]
        self._password = user_input[CONF_PASSWORD]
        self._include_orphan_channels = user_input[CONF_INCLUDE_ORPHAN_CHANNELS]
        self._include_virtual_devices = user_input[CONF_INCLUDE_VIRTUAL_DEVICES]
        self._create_subdevices = user_input[CONF_CREATE_SUBDEVICES]
        self._ssl_cert_path = user_input.get(CONF_SSL_CERT_PATH)

        return self._async_update_reload_and_abort()

    @callback
    def _async_show_setup_form(
        self,
        step_id: str,
        errors: dict[str, str] | None = None,
        host: str | None = None,
        username: str | None = None,
        include_orphan_channels: bool = False,
        include_virtual_devices: bool = False,
        create_subdevices: bool = False,
        ssl_cert_path: str | None = None,
    ) -> ConfigFlowResult:
        """Show the setup form to the user."""
        description_placeholders: Mapping[str, str | None] = {}

        if self._host:
            description_placeholders[CONF_HOST] = self._host
        if self._serial_number:
            description_placeholders[CONF_SERIAL] = self._serial_number
        if self._name:
            description_placeholders[CONF_NAME] = self._name
        if self._sysap_version:
            description_placeholders[SYSAP_VERSION] = self._sysap_version

        return self.async_show_form(
            step_id=step_id,
            data_schema=_schema_with_defaults(
                step_id=step_id,
                host=host,
                username=username,
                include_orphan_channels=include_orphan_channels,
                include_virtual_devices=include_virtual_devices,
                create_subdevices=create_subdevices,
                ssl_cert_path=ssl_cert_path,
            ),
            errors=errors or {},
            description_placeholders=description_placeholders,
        )

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
                CONF_SSL_CERT_PATH: self._ssl_cert_path,
            },
        )

    @callback
    def _async_update_reload_and_abort(self) -> ConfigFlowResult:
        return self.async_update_reload_and_abort(
            self._get_reconfigure_entry(),
            data_updates={
                CONF_USERNAME: self._username,
                CONF_PASSWORD: self._password,
                CONF_INCLUDE_ORPHAN_CHANNELS: self._include_orphan_channels,
                CONF_INCLUDE_VIRTUAL_DEVICES: self._include_virtual_devices,
                CONF_CREATE_SUBDEVICES: self._create_subdevices,
                CONF_SSL_CERT_PATH: self._ssl_cert_path,
            },
        )
