"""Diagnostics support for ABB-free@home."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from abbfreeathome.bin.function import Function
from abbfreeathome.bin.pairing import Pairing
from abbfreeathome.bin.parameter import Parameter
from abbfreeathome.freeathome import FreeAtHome

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {"latitude", "longitude", "sysapName", "uartSerialNumber"}


def inject_function_pairing_parameter_names(device_list: list[dict]):
    """Inject the function, pairaing and parameter names into the list of devices."""

    for _device_value in device_list.values():
        _device_value["parameterNames"] = {}
        for _device_param_key, _device_param_value in _device_value.get(
            "parameters"
        ).items():
            try:
                _device_value["parameterNames"][
                    f"{Parameter(int(_device_param_key.lstrip("par"), 16)).name} ({_device_param_key})"
                ] = _device_param_value
            except ValueError:  # noqa: PERF203
                _device_value["parameterNames"][f"UNKNOWN ({_device_param_key})"] = (
                    _device_param_value
                )

        for _channel_key, _channel_value in _device_value.get("channels").items():
            for _input_key, _input_value in _channel_value.get("inputs").items():
                try:
                    _input_value["pairing"] = Pairing(
                        _input_value.get("pairingID")
                    ).name
                except ValueError:
                    _input_value["pairing"] = "UNKNOWN"

                _channel_value["inputs"][_input_key] = OrderedDict(
                    sorted(_input_value.items())
                )

            for _output_key, _output_value in _channel_value.get("outputs").items():
                try:
                    _output_value["pairing"] = Pairing(
                        _output_value.get("pairingID")
                    ).name
                except ValueError:
                    _output_value["pairing"] = "UNKNOWN"

                _channel_value["outputs"][_output_key] = OrderedDict(
                    sorted(_output_value.items())
                )

            _channel_value["parameterNames"] = {}
            for _channel_param_key, _channel_param_value in _channel_value.get(
                "parameters"
            ).items():
                try:
                    _channel_value["parameterNames"][
                        f"{Parameter(int(_channel_param_key.lstrip("par"), 16)).name} ({_channel_param_key})"
                    ] = _channel_param_value
                except ValueError:  # noqa: PERF203
                    _channel_value["parameterNames"][
                        f"UNKNOWN ({_channel_param_key})"
                    ] = _channel_param_value

            try:
                _channel_value["function"] = Function(
                    int(_channel_value.get("functionID"), 16)
                ).name
            except ValueError:
                _channel_value["function"] = "UNKNOWN"

            _device_value["channels"][_channel_key] = OrderedDict(
                sorted(_channel_value.items())
            )


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    _free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]

    # Inject Function and Pairing names into configuration.
    inject_function_pairing_parameter_names(
        (await _free_at_home.get_config()).get("devices")
    )

    return async_redact_data(await _free_at_home.get_config(), TO_REDACT)
