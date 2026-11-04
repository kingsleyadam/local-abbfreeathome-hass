"""Constants for the ABB-free@home integration."""

from datetime import timedelta

DOMAIN = "abbfreeathome_ci"
MANUFACTURER = "ABB Busch-Jaeger"

# Domain Configuration
CONF_SERIAL = "serial"
CONF_INCLUDE_ORPHAN_CHANNELS = "include_orphan_channels"
CONF_INCLUDE_VIRTUAL_DEVICES = "include_virtual_devices"
CONF_CREATE_SUBDEVICES = "create_subdevices"
CONF_SSL_CERT_FILE_PATH = "ssl_cert_file_path"
CONF_VERIFY_SSL = "verify_ssl"
CONF_CREATE_UNRESPONSIVE_REPAIRS = "create_unresponsive_repairs"

# Repair issue for unresponsive devices, created after this grace period
UNRESPONSIVE_REPAIR_DELAY = timedelta(minutes=5)

# SysAP Settings
SYSAP_VERSION = "sysap_version"

# Service Calls
VIRTUAL_DEVICE = "virtual_device"
LIST_VIRTUAL_DEVICES = "list_virtual_devices"
