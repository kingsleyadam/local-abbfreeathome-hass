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

from .const import CONF_SERIAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _schema_with_defaults(host: str | None = None, step_id: str = "user") -> vol.Schema:
    schema = vol.Schema({})

    if step_id == "user":
        schema = schema.extend({vol.Required(CONF_HOST, default=host): str})

    return schema.extend(
        {
            vol.Required(CONF_USERNAME, default="installer"): str,
            vol.Required(CONF_PASSWORD): str,
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


class ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ABB free@home."""

    VERSION = 1
    CONNECTION_CLASS = CONN_CLASS_LOCAL_PUSH

    _host: str = None
    _name: str = None
    _password: str = None
    _serial_number: str = None
    _title: str = None
    _username: str = None

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

        return self._async_create_entry()

    @callback
    def _async_show_setup_form(
        self, step_id: str, errors: dict[str, str] | None = None
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
            data_schema=_schema_with_defaults(step_id=step_id),
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
            },
        )
