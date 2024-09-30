"""Config flow for ABB free@home integration."""

from __future__ import annotations

import logging
from typing import Any

from abbfreeathome.api import (
    ForbiddenAuthException,
    FreeAtHomeApi,
    InvalidCredentialsException,
    InvalidHostException,
)
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
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

    _LOGGER.info(sysap)
    _LOGGER.info(settings.get("flags").get("serialNumber"))

    # Return info that you want to store in the config entry.
    return {"title": settings.get("flags").get("serialNumber")}


class ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ABB free@home."""

    VERSION = 1

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

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
