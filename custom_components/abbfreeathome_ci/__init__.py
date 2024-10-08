"""The ABB free@home integration."""

from __future__ import annotations

from abbfreeathome.api import FreeAtHomeApi
from abbfreeathome.freeathome import FreeAtHome

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN

PLATFORMS: list[Platform] = [Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ABB free@home from a config entry."""

    _free_at_home = FreeAtHome(
        api=FreeAtHomeApi(
            host=entry.data[CONF_HOST],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
        )
    )

    # Verify we can fetch the config from the api
    await _free_at_home.get_config()

    # Load devices into the free at home object
    await _free_at_home.load_devices()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = _free_at_home
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_create_background_task(hass, _free_at_home.ws_listen(), f"{DOMAIN}_ws")

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Close websocket connection
    free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]
    await free_at_home.ws_close()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
