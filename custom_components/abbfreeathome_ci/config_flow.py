"""Config flow for ABB free@home integration."""

from __future__ import annotations

from collections.abc import Mapping
from ipaddress import IPv4Address
import logging
from typing import Any

from abbfreeathome.api import (
    ForbiddenAuthException,
    FreeAtHomeApi,
    FreeAtHomeSettings,
    InvalidCredentialsException,
    InvalidHostException,
)
import voluptuous as vol

from homeassistant.components import zeroconf
from homeassistant.config_entries import (
    CONN_CLASS_LOCAL_PUSH,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback

from .const import CONF_INCLUDE_ORPHAN_CHANNELS, CONF_SERIAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _schema_with_defaults(
    host: str | None = None,
    username: str | None = None,
    include_orphan_channels: bool = False,
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
        }
    )


async def validate_settings(host: str) -> dict[str, Any]:
    """Validate the settings endpoint."""
    errors: dict[str, str] = {}
    settings: FreeAtHomeSettings = FreeAtHomeSettings(host=host)

    try:
        await settings.load()
    except InvalidHostException:
        errors["base"] = "cannot_connect"

    return settings.name, settings.serial_number, errors


async def validate_api(host: str, username: str, password: str) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    errors: dict[str, str] = {}
    api = FreeAtHomeApi(host=host, username=username, password=password)

    try:
        await api.get_sysap()
    except InvalidCredentialsException:
        errors["base"] = "invalid_auth"
    except ForbiddenAuthException:
        errors["base"] = "invalid_auth"
    except InvalidHostException:
        errors["base"] = "cannot_connect"
    except Exception:
        _LOGGER.exception("Unexpected exception")
        errors["base"] = "unknown"

    return errors


class FreeAtHomeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ABB free@home."""

    VERSION = 1
    MINOR_VERSION = 2
    CONNECTION_CLASS = CONN_CLASS_LOCAL_PUSH

    def __init__(self) -> None:
        """Initialize."""
        self._host: str | None = None
        self._name: str | None = None
        self._password: str | None = None
        self._serial_number: str | None = None
        self._title: str | None = None
        self._username: str | None = None
        self._include_orphan_channels: bool = False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial user step."""
        if user_input is None:
            return self._async_show_setup_form(step_id="user")

        name, serial_number, settings_errors = await validate_settings(
            host=user_input[CONF_HOST]
        )
        api_errors = await validate_api(
            host=user_input[CONF_HOST],
            username=user_input[CONF_USERNAME],
            password=user_input[CONF_PASSWORD],
        )
        errors = settings_errors | api_errors

        if errors:
            return self._async_show_setup_form(step_id="user", errors=errors)

        await self.async_set_unique_id(serial_number)
        self._abort_if_unique_id_configured()

        self._serial_number = serial_number
        self._name = name
        self._title = f"{name} ({serial_number})"

        self._host = user_input[CONF_HOST]
        self._username = user_input[CONF_USERNAME]
        self._password = user_input[CONF_PASSWORD]
        self._include_orphan_channels = user_input[CONF_INCLUDE_ORPHAN_CHANNELS]

        return self._async_create_entry()

    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle zeroconf discovery."""
        if not isinstance(discovery_info.ip_address, IPv4Address):
            return self.async_abort(reason="not_ipv4address")

        self._host = f"http://{discovery_info.ip_address.exploded}"
        name, serial_number, errors = await validate_settings(host=self._host)

        self._serial_number = serial_number
        self._name = name
        self._title = f"{name} ({serial_number})"

        if errors:
            return self.async_abort(reason="invalid_settings")

        await self.async_set_unique_id(serial_number)
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
        )

        if errors:
            return self._async_show_setup_form(
                step_id="zeroconf_confirm", errors=errors
            )

        self._username = user_input[CONF_USERNAME]
        self._password = user_input[CONF_PASSWORD]
        self._include_orphan_channels = user_input[CONF_INCLUDE_ORPHAN_CHANNELS]

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

        if user_input is None:
            return self._async_show_setup_form(
                step_id="reconfigure",
                username=self._username,
                include_orphan_channels=self._include_orphan_channels,
            )

        errors = await validate_api(
            host=self._host,
            username=user_input[CONF_USERNAME],
            password=user_input[CONF_PASSWORD],
        )

        if errors:
            return self._async_show_setup_form(step_id="reconfigure", errors=errors)

        self._username = user_input[CONF_USERNAME]
        self._password = user_input[CONF_PASSWORD]
        self._include_orphan_channels = user_input[CONF_INCLUDE_ORPHAN_CHANNELS]

        return self._async_update_reload_and_abort()

    @callback
    def _async_show_setup_form(
        self,
        step_id: str,
        errors: dict[str, str] | None = None,
        host: str | None = None,
        username: str | None = None,
        include_orphan_channels: bool = False,
    ) -> ConfigFlowResult:
        """Show the setup form to the user."""
        description_placeholders: Mapping[str, str | None] = {}

        if self._host:
            description_placeholders[CONF_HOST] = self._host
        if self._serial_number:
            description_placeholders[CONF_SERIAL] = self._serial_number
        if self._name:
            description_placeholders[CONF_NAME] = self._name

        return self.async_show_form(
            step_id=step_id,
            data_schema=_schema_with_defaults(
                step_id=step_id,
                host=host,
                username=username,
                include_orphan_channels=include_orphan_channels,
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
            },
        )
