"""Config flow for ABB free@home integration."""

from __future__ import annotations

from ipaddress import IPv4Address
import logging
from typing import Any

from abbfreeathome.api import (
    ForbiddenAuthException,
    FreeAtHomeApi,
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
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _schema_with_defaults(
    host: str | None = None, name: str | None = None
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=host): str,
            vol.Required(CONF_USERNAME, default="installer"): str,
            vol.Required(CONF_PASSWORD): str,
        }
    )


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from schema with values provided by the user.
    """
    api = FreeAtHomeApi(
        host=data[CONF_HOST], username=data[CONF_USERNAME], password=data[CONF_PASSWORD]
    )

    try:
        sysap = await api.get_sysap()
        settings = await api.get_settings()
    except InvalidCredentialsException as ex:
        raise InvalidAuth from ex
    except ForbiddenAuthException as ex:
        raise InvalidAuth from ex
    except InvalidHostException as ex:
        raise CannotConnect from ex

    sysap_name = sysap.get("sysapName")
    sysap_serial_number = settings.get("flags").get("serialNumber")

    if sysap_name and sysap_serial_number:
        sysap_title = f"{sysap_name} ({sysap_serial_number})"
    else:
        sysap_title = sysap_serial_number

    # Return info that you want to store in the config entry.
    return {"title": sysap_title}


class ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ABB free@home."""

    VERSION = 1
    CONNECTION_CLASS = CONN_CLASS_LOCAL_PUSH

    def __init__(self) -> None:
        """Initialize the Free@Home config flow."""
        self.discovery_schema: vol.Schema | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        data = self.discovery_schema or _schema_with_defaults()
        return self.async_show_form(step_id="user", data_schema=data, errors=errors)

    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle zeroconf discovery."""
        if not isinstance(discovery_info.ip_address, IPv4Address):
            return self.async_abort(reason="not_ipv4address")

        # Set the free@home api endpoint
        fah_endpoint = f"http://{discovery_info.ip_address.exploded}"

        # Set uniqueness of the config flow, or update fah endpoint if changed.
        await self.async_set_unique_id(discovery_info.name)
        self._abort_if_unique_id_configured(updates={CONF_HOST: fah_endpoint})

        # Set the discovery schema to show to the user.
        self.discovery_schema = _schema_with_defaults(host=fah_endpoint)

        self.context["title_placeholders"] = {
            CONF_HOST: fah_endpoint,
        }

        return await self.async_step_user()


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
