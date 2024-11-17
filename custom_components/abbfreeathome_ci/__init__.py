"""The ABB-free@home integration."""

from __future__ import annotations

import logging

from abbfreeathome.api import FreeAtHomeApi, FreeAtHomeSettings
from abbfreeathome.bin.interface import Interface
from abbfreeathome.freeathome import FreeAtHome

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_INCLUDE_ORPHAN_CHANNELS, CONF_SERIAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.EVENT,
    Platform.LIGHT,
    Platform.LOCK,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.VALVE,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ABB-free@home from a config entry."""

    # Get settings from free@home SysAP
    _free_at_home_settings = FreeAtHomeSettings(host=entry.data[CONF_HOST])
    await _free_at_home_settings.load()

    # Attempt to fetch orphan channels config entry, if not found fallback to True
    try:
        _include_orphan_channels = entry.data[CONF_INCLUDE_ORPHAN_CHANNELS]
    except KeyError:
        _include_orphan_channels = True

    # Create the FreeAtHome Object
    _free_at_home = FreeAtHome(
        api=FreeAtHomeApi(
            host=entry.data[CONF_HOST],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
        ),
        interfaces=[
            Interface.UNDEFINED,
            Interface.WIRED_BUS,
            Interface.WIRELESS_RF,
            Interface.VIRTUAL_DEVICE,
        ],
        include_orphan_channels=_include_orphan_channels,
    )

    # Verify we can fetch the config from the api
    await _free_at_home.get_config()

    # Load devices into the free at home object
    await _free_at_home.load_devices()

    # Register SysAP as a Device
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.data[CONF_SERIAL])},
        manufacturer="ABB Busch-Jaeger",
        model="System Access Point",
        name=_free_at_home_settings.name,
        serial_number=entry.data[CONF_SERIAL],
        sw_version=_free_at_home_settings.version,
        hw_version=_free_at_home_settings.hardware_version,
        configuration_url=entry.data[CONF_HOST],
    )

    # Add the FreeAtHome object to hass data
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = _free_at_home

    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Create a websocket connection for listen for changes in device entities.
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


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Remove a config entry from a device."""

    # Fetch the device serial.
    device_serial = next(
        iter(value for key, value in device_entry.identifiers if key == DOMAIN)
    )

    # Unload the device from the FreeAtHome class
    free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]
    free_at_home.unload_device_by_device_serial(device_serial)

    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug(
        "Migrating configuration from version %s.%s",
        entry.version,
        entry.minor_version,
    )

    if entry.version > 1:
        # This means the user has downgraded from a future version
        return False

    if entry.version == 1:
        new_data = {**entry.data}

        if entry.minor_version < 2:
            new_data[CONF_INCLUDE_ORPHAN_CHANNELS] = True

        hass.config_entries.async_update_entry(
            entry, data=new_data, version=1, minor_version=2
        )

    _LOGGER.debug(
        "Migration to configuration version %s.%s successful",
        entry.version,
        entry.minor_version,
    )

    return True
