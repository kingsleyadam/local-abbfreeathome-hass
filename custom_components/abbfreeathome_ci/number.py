"""Create ABB-free@home number entities."""

from typing import Any

from abbfreeathome.devices.virtual.virtual_brightness_sensor import (
    VirtualBrightnessSensor,
)
from abbfreeathome.devices.virtual.virtual_energy_battery import VirtualEnergyBattery
from abbfreeathome.devices.virtual.virtual_energy_inverter import VirtualEnergyInverter
from abbfreeathome.devices.virtual.virtual_energy_two_way_meter import (
    VirtualEnergyTwoWayMeter,
)
from abbfreeathome.devices.virtual.virtual_temperature_sensor import (
    VirtualTemperatureSensor,
)
from abbfreeathome.devices.virtual.virtual_wind_sensor import VirtualWindSensor
from abbfreeathome.freeathome import FreeAtHome

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    LIGHT_LUX,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SERIAL, DOMAIN

NUMBER_DESCRIPTIONS = {
    "VirtualBrightnessSensor": {
        "device_class": VirtualBrightnessSensor,
        "value_attribute": "brightness",
        "entity_description_kwargs": {
            "device_class": NumberDeviceClass.ILLUMINANCE,
            "translation_key": "virtual_brightness_sensor",
            "native_max_value": 1000000.0,
            "native_min_value": 0.0,
            "native_step": 1.0,
            "native_unit_of_measurement": LIGHT_LUX,
        },
    },
    "VirtualEnergyBatteryBatteryPower": {
        "device_class": VirtualEnergyBattery,
        "value_attribute": "battery_power",
        "entity_description_kwargs": {
            "device_class": NumberDeviceClass.POWER,
            "translation_key": "virtual_energy_battery_battery_power",
            "native_max_value": 99999.999,
            "native_min_value": -99999.999,
            "native_step": 0.001,
            "native_unit_of_measurement": UnitOfPower.KILO_WATT,
        },
    },
    "VirtualEnergyBatterySoc": {
        "device_class": VirtualEnergyBattery,
        "value_attribute": "soc",
        "entity_description_kwargs": {
            "device_class": None,
            "translation_key": "virtual_energy_battery_soc",
            "native_max_value": 100.0,
            "native_min_value": 0.0,
            "native_step": 1.0,
            "native_unit_of_measurement": "%",
        },
    },
    "VirtualEnergyBatteryImportedToday": {
        "device_class": VirtualEnergyBattery,
        "value_attribute": "imported_today",
        "entity_description_kwargs": {
            "device_class": NumberDeviceClass.ENERGY,
            "translation_key": "virtual_energy_battery_imported_today",
            "native_max_value": 1000000000.0,
            "native_min_value": 0.0,
            "native_step": 1.0,
            "native_unit_of_measurement": UnitOfEnergy.WATT_HOUR,
        },
    },
    "VirtualEnergyBatteryExportedToday": {
        "device_class": VirtualEnergyBattery,
        "value_attribute": "exported_today",
        "entity_description_kwargs": {
            "device_class": NumberDeviceClass.ENERGY,
            "translation_key": "virtual_energy_battery_exported_today",
            "native_max_value": 1000000000.0,
            "native_min_value": 0.0,
            "native_step": 1.0,
            "native_unit_of_measurement": UnitOfEnergy.WATT_HOUR,
        },
    },
    "VirtualEnergyBatteryImportedTotal": {
        "device_class": VirtualEnergyBattery,
        "value_attribute": "imported_total",
        "entity_description_kwargs": {
            "device_class": NumberDeviceClass.ENERGY,
            "translation_key": "virtual_energy_battery_imported_total",
            "native_max_value": 1000000000.0,
            "native_min_value": 0.0,
            "native_step": 1.0,
            "native_unit_of_measurement": UnitOfEnergy.WATT_HOUR,
        },
    },
    "VirtualEnergyBatteryExportedTotal": {
        "device_class": VirtualEnergyBattery,
        "value_attribute": "exported_total",
        "entity_description_kwargs": {
            "device_class": NumberDeviceClass.ENERGY,
            "translation_key": "virtual_energy_battery_exported_total",
            "native_max_value": 1000000000.0,
            "native_min_value": 0.0,
            "native_step": 1.0,
            "native_unit_of_measurement": UnitOfEnergy.WATT_HOUR,
        },
    },
    "VirtualEnergyInverterCurrentPower": {
        "device_class": VirtualEnergyInverter,
        "value_attribute": "current_power",
        "entity_description_kwargs": {
            "device_class": NumberDeviceClass.POWER,
            "translation_key": "virtual_energy_inverter_current_power",
            "native_max_value": 99999.9,
            "native_min_value": -99999.9,
            "native_step": 0.1,
            "native_unit_of_measurement": UnitOfPower.WATT,
        },
    },
    "VirtualEnergyInverterImportedToday": {
        "device_class": VirtualEnergyInverter,
        "value_attribute": "imported_today",
        "entity_description_kwargs": {
            "device_class": NumberDeviceClass.ENERGY,
            "translation_key": "virtual_energy_inverter_imported_today",
            "native_max_value": 1000000000.0,
            "native_min_value": 0.0,
            "native_step": 1.0,
            "native_unit_of_measurement": UnitOfEnergy.WATT_HOUR,
        },
    },
    "VirtualEnergyInverterImportedTotal": {
        "device_class": VirtualEnergyInverter,
        "value_attribute": "imported_total",
        "entity_description_kwargs": {
            "device_class": NumberDeviceClass.ENERGY,
            "translation_key": "virtual_energy_inverter_imported_total",
            "native_max_value": 1000000000.0,
            "native_min_value": 0.0,
            "native_step": 1.0,
            "native_unit_of_measurement": UnitOfEnergy.WATT_HOUR,
        },
    },
    "VirtualEnergyTwoWayMeterCurrentPower": {
        "device_class": VirtualEnergyTwoWayMeter,
        "value_attribute": "current_power",
        "entity_description_kwargs": {
            "device_class": NumberDeviceClass.POWER,
            "translation_key": "virtual_energy_two_way_meter_current_power",
            "native_max_value": 99999.9,
            "native_min_value": -99999.9,
            "native_step": 0.1,
            "native_unit_of_measurement": UnitOfPower.WATT,
        },
    },
    "VirtualEnergyTwoMayMeterImportedToday": {
        "device_class": VirtualEnergyTwoWayMeter,
        "value_attribute": "imported_today",
        "entity_description_kwargs": {
            "device_class": NumberDeviceClass.ENERGY,
            "translation_key": "virtual_energy_two_way_meter_imported_today",
            "native_max_value": 1000000000.0,
            "native_min_value": 0.0,
            "native_step": 1.0,
            "native_unit_of_measurement": UnitOfEnergy.WATT_HOUR,
        },
    },
    "VirtualEnergyTwoMayMeterExportedToday": {
        "device_class": VirtualEnergyTwoWayMeter,
        "value_attribute": "exported_today",
        "entity_description_kwargs": {
            "device_class": NumberDeviceClass.ENERGY,
            "translation_key": "virtual_energy_two_way_meter_exported_today",
            "native_max_value": 1000000000.0,
            "native_min_value": 0.0,
            "native_step": 1.0,
            "native_unit_of_measurement": UnitOfEnergy.WATT_HOUR,
        },
    },
    "VirtualEnergyTwoMayMeterImportedTotal": {
        "device_class": VirtualEnergyTwoWayMeter,
        "value_attribute": "imported_total",
        "entity_description_kwargs": {
            "device_class": NumberDeviceClass.ENERGY,
            "translation_key": "virtual_energy_two_way_meter_imported_total",
            "native_max_value": 1000000000.0,
            "native_min_value": 0.0,
            "native_step": 1.0,
            "native_unit_of_measurement": UnitOfEnergy.WATT_HOUR,
        },
    },
    "VirtualEnergyTwoMayMeterExportedTotal": {
        "device_class": VirtualEnergyTwoWayMeter,
        "value_attribute": "exported_total",
        "entity_description_kwargs": {
            "device_class": NumberDeviceClass.ENERGY,
            "translation_key": "virtual_energy_two_way_meter_exported_total",
            "native_max_value": 1000000000.0,
            "native_min_value": 0.0,
            "native_step": 1.0,
            "native_unit_of_measurement": UnitOfEnergy.WATT_HOUR,
        },
    },
    "VirtualTemperatureSensor": {
        "device_class": VirtualTemperatureSensor,
        "value_attribute": "temperature",
        "entity_description_kwargs": {
            "device_class": NumberDeviceClass.TEMPERATURE,
            "translation_key": "virtual_temperature_sensor",
            "native_max_value": 999.9,
            "native_min_value": -999.9,
            "native_step": 0.1,
            "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
        },
    },
    "VirtualWindSensorForce": {
        "device_class": VirtualWindSensor,
        "value_attribute": "force",
        "entity_description_kwargs": {
            "device_class": NumberDeviceClass.WIND_SPEED,
            "translation_key": "virtual_wind_sensor_force",
            "native_max_value": 12.0,
            "native_min_value": 0.0,
            "native_step": 1.0,
            "native_unit_of_measurement": UnitOfSpeed.BEAUFORT,
        },
    },
    "VirtualWindSensorSpeed": {
        "device_class": VirtualWindSensor,
        "value_attribute": "speed",
        "entity_description_kwargs": {
            "device_class": NumberDeviceClass.WIND_SPEED,
            "translation_key": "virtual_wind_sensor_speed",
            "native_max_value": 999.9,
            "native_min_value": 0.0,
            "native_step": 0.1,
            "native_unit_of_measurement": UnitOfSpeed.METERS_PER_SECOND,
        },
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up numbers."""
    free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]

    for key, description in NUMBER_DESCRIPTIONS.items():
        async_add_entities(
            FreeAtHomeNumberEntity(
                device,
                value_attribute=description.get("value_attribute"),
                entity_description_kwargs={"key": key}
                | description.get("entity_description_kwargs"),
                sysap_serial_number=entry.data[CONF_SERIAL],
            )
            for device in free_at_home.get_devices_by_class(
                device_class=description.get("device_class")
            )
            if getattr(device, description.get("value_attribute")) is not None
        )


class FreeAtHomeNumberEntity(NumberEntity):
    """Defines a free@home number entity."""

    _attr_should_poll: bool = False

    def __init__(
        self,
        device: VirtualBrightnessSensor | VirtualTemperatureSensor,
        value_attribute: str,
        entity_description_kwargs: dict[str:Any],
        sysap_serial_number: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__()
        self._device = device
        self._value_attribute = value_attribute
        self._sysap_serial_number = sysap_serial_number

        self.entity_description = NumberEntityDescription(
            has_entity_name=True,
            name=device.channel_name,
            translation_placeholders={"channel_id": device.channel_id},
            **entity_description_kwargs,
        )

    async def async_added_to_hass(self) -> None:
        """Run when this entity has been added to HA."""
        self._device.register_callback(
            callback_attribute=self._value_attribute, callback=self.async_write_ha_state
        )

    async def async_will_remove_from_hass(self) -> None:
        """Entity beeing removed from hass."""
        self._device.remove_callback(
            callback_attribute=self._value_attribute, callback=self.async_write_ha_state
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._device.device_id)},
            "name": self._device.device_name,
            "manufacturer": "ABB busch-jaeger",
            "serial_number": self._device.device_id,
            "suggested_area": self._device.room_name,
            "via_device": (DOMAIN, self._sysap_serial_number),
        }

    @property
    def native_value(self) -> float | None:
        """Return value of the number."""
        return getattr(self._device, self._value_attribute)

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._device.device_id}_{self._device.channel_id}_{self.entity_description.key}"

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value.

        This is especially needed as there are devices (virtual) with multiple numbers to set.
        """
        _method_to_call = "set_" + self._value_attribute
        await getattr(self._device, _method_to_call)(float(value))

    async def async_update(self, **kwargs: Any) -> None:
        """Update the number state."""
        await self._device.refresh_state()
