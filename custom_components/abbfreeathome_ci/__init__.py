"""The ABB-free@home integration."""

from __future__ import annotations

import logging

from abbfreeathome import FreeAtHome, FreeAtHomeApi
from abbfreeathome.api import (
    VIRTUAL_DEVICE_PROPERTIES_SCHEMA,
    VIRTUAL_DEVICE_ROOT_SCHEMA,
    FreeAtHomeSettings,
)
from abbfreeathome.bin.interface import Interface
from abbfreeathome.exceptions import BadRequestException
import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    ServiceValidationError,
    SupportsResponse,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_CREATE_SUBDEVICES,
    CONF_INCLUDE_ORPHAN_CHANNELS,
    CONF_INCLUDE_VIRTUAL_DEVICES,
    CONF_SERIAL,
    CONF_SSL_CERT_PATH,
    DOMAIN,
    MANUFACTURER,
    VIRTUAL_DEVICE,
)

VIRTUALDEVICE_SCHEMA = (
    vol.Schema(
        {
            vol.Required("serial"): str,
        }
    )
    .extend(VIRTUAL_DEVICE_ROOT_SCHEMA.schema)
    .extend(VIRTUAL_DEVICE_PROPERTIES_SCHEMA.schema)
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.EVENT,
    Platform.LIGHT,
    Platform.LOCK,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.VALVE,
]

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Optional(CONF_INCLUDE_ORPHAN_CHANNELS, default=False): cv.boolean,
                vol.Optional(CONF_INCLUDE_VIRTUAL_DEVICES, default=False): cv.boolean,
                vol.Optional(CONF_CREATE_SUBDEVICES, default=False): cv.boolean,
                vol.Optional(CONF_SSL_CERT_PATH): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up abbfreeathome instance."""
    # If no config entry found in yaml, return True
    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data=conf,
        )
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ABB-free@home from a config entry."""

    # Get the Home Assistant ClientSession Object
    _client_session = async_get_clientsession(hass)

    # Get SSL certificate configuration
    _ssl_cert_path = entry.data.get(CONF_SSL_CERT_PATH)
    _verify_ssl = bool(_ssl_cert_path)

    # If SSL certificate path is provided, force verify_ssl to True
    if _ssl_cert_path and _ssl_cert_path.strip():
        _verify_ssl = True

    # Log SSL configuration warnings
    _host = entry.data[CONF_HOST]
    if _host.startswith("https://"):
        if not _ssl_cert_path:
            _LOGGER.warning(
                "HTTPS connection without SSL certificate path - SSL verification will be disabled. "
                "This connection may not be secure. Consider providing an SSL certificate path for verification."
            )
        else:
            _LOGGER.info("HTTPS connection with SSL certificate verification enabled")

    # Get settings from free@home SysAP
    _free_at_home_settings = FreeAtHomeSettings(
        host=entry.data[CONF_HOST],
        client_session=_client_session,
        verify_ssl=_verify_ssl,
        ssl_cert_ca_file=_ssl_cert_path,
    )
    await _free_at_home_settings.load()

    # Attempt to fetch orphan channels config entry, if not found fallback to True
    try:
        _include_orphan_channels = entry.data[CONF_INCLUDE_ORPHAN_CHANNELS]
    except KeyError:
        _include_orphan_channels = True

    # Define the basic interfaces to be included
    _interfaces = [
        Interface.UNDEFINED,
        Interface.WIRED_BUS,
        Interface.WIRELESS_RF,
        Interface.SMOKEALARM,
    ]

    # Attempt to fetch virtual devices config entry, if not found fallback to False
    try:
        _include_virtual_devices = entry.data[CONF_INCLUDE_VIRTUAL_DEVICES]
    except KeyError:
        _include_virtual_devices = False

    if _include_virtual_devices:
        _interfaces.append(Interface.VIRTUAL_DEVICE)

    # Create the FreeAtHome Object
    _free_at_home = FreeAtHome(
        api=FreeAtHomeApi(
            host=entry.data[CONF_HOST],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            client_session=_client_session,
            verify_ssl=_verify_ssl,
            ssl_cert_ca_file=_ssl_cert_path,
        ),
        interfaces=_interfaces,
        include_orphan_channels=_include_orphan_channels,
    )

    # Verify we can fetch the config from the api
    await _free_at_home.get_config()

    # Load devices into the free at home object
    await _free_at_home.load()

    # Register SysAP as a Device
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.data[CONF_SERIAL])},
        manufacturer=MANUFACTURER,
        model="System Access Point",
        name=_free_at_home_settings.name,
        serial_number=entry.data[CONF_SERIAL],
        sw_version=_free_at_home_settings.version,
        hw_version=_free_at_home_settings.hardware_version,
        configuration_url=entry.data[CONF_HOST],
    )

    for _device in _free_at_home.get_devices().values():
        if not _free_at_home.get_channels_by_device(_device.device_serial):
            continue

        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, _device.device_serial)},
            name=_device.display_name,
            manufacturer=MANUFACTURER,
            serial_number=_device.device_serial,
            hw_version=_device.device_id,
            suggested_area=_device.room_name,
            via_device=(DOMAIN, entry.data[CONF_SERIAL]),
        )

    # Add the FreeAtHome object to hass data
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = _free_at_home

    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Create a websocket connection for listen for changes in device entities.
    entry.async_create_background_task(hass, _free_at_home.ws_listen(), f"{DOMAIN}_ws")

    # Setup services
    if not hass.services.has_service(DOMAIN, VIRTUAL_DEVICE):
        await async_setup_service(hass, entry)

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
    free_at_home.unload_device(device_serial)

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

        if entry.minor_version < 3:
            new_data[CONF_INCLUDE_VIRTUAL_DEVICES] = False

        hass.config_entries.async_update_entry(
            entry, data=new_data, version=1, minor_version=3
        )

        if entry.minor_version < 4:
            new_data[CONF_CREATE_SUBDEVICES] = False

        hass.config_entries.async_update_entry(
            entry, data=new_data, version=1, minor_version=4
        )

        if entry.minor_version < 5:
            # Add SSL certificate path support - default to None
            if CONF_SSL_CERT_PATH not in new_data:
                new_data[CONF_SSL_CERT_PATH] = None

        hass.config_entries.async_update_entry(
            entry, data=new_data, version=1, minor_version=5
        )

    _LOGGER.debug(
        "Migration to configuration version %s.%s successful",
        entry.version,
        entry.minor_version,
    )

    return True


async def async_setup_service(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up services for ABB-free@home integration."""

    async def virtual_device(call: ServiceCall) -> ServiceResponse:
        """Service call to interact with the virtualdevice REST endpoint."""

        # At this point the validation was successful and the dict can be constructed
        data = {
            "type": call.data.get("type"),
            "properties": {
                "ttl": call.data.get("ttl"),
            },
        }

        if "displayname" in call.data:
            data["properties"]["displayname"] = call.data.get("displayname")
        if "flavor" in call.data:
            data["properties"]["flavor"] = call.data.get("flavor")
        if "capabilities" in call.data:
            data["properties"]["capabilities"] = call.data.get("capabilities")

        _fah = hass.data[DOMAIN][entry.entry_id]

        try:
            _result = await _fah.api.virtualdevice(
                serial=call.data.get("serial"),
                data=data,
            )
        except BadRequestException as e:
            raise ServiceValidationError(e.message) from e

        return _result

    hass.services.async_register(
        DOMAIN,
        VIRTUAL_DEVICE,
        virtual_device,
        schema=VIRTUALDEVICE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
