"""Create ABB-free@home number entities."""

from typing import Any

from abbfreeathome.bin.pairing import Pairing
from abbfreeathome.channels.base import Base
from abbfreeathome.channels.virtual.virtual_brightness_sensor import (
    VirtualBrightnessSensor,
)
from abbfreeathome.channels.virtual.virtual_energy_battery import VirtualEnergyBattery
from abbfreeathome.channels.virtual.virtual_energy_inverter import VirtualEnergyInverter
from abbfreeathome.channels.virtual.virtual_energy_two_way_meter import (
    VirtualEnergyTwoWayMeter,
)
from abbfreeathome.channels.virtual.virtual_room_temperature_controller import (
    VirtualRoomTemperatureController,
)
from abbfreeathome.channels.virtual.virtual_temperature_sensor import (
    VirtualTemperatureSensor,
)
from abbfreeathome.channels.virtual.virtual_wind_sensor import VirtualWindSensor
from abbfreeathome.exceptions import InvalidDeviceChannelPairing

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

from .const import CONF_CREATE_SUBDEVICES, CONF_SERIAL, DOMAIN
from .entity import ChannelGetter, FreeAtHomeEntity, async_setup_platform_entities
from .helpers import AnyDeviceInfo, async_get_sub_device_info

NUMBER_DESCRIPTIONS = {
    "VirtualBrightnessSensor": {
        "channel_class": VirtualBrightnessSensor,
        "value_attribute": "brightness",
        "output_pairing": Pairing.AL_BRIGHTNESS_LEVEL,
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
        "channel_class": VirtualEnergyBattery,
        "value_attribute": "battery_power",
        "output_pairing": Pairing.AL_BATTERY_POWER,
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
        "channel_class": VirtualEnergyBattery,
        "value_attribute": "soc",
        "output_pairing": Pairing.AL_SOC,
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
        "channel_class": VirtualEnergyBattery,
        "value_attribute": "imported_today",
        "output_pairing": Pairing.AL_MEASURED_IMPORTED_ENERGY_TODAY,
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
        "channel_class": VirtualEnergyBattery,
        "value_attribute": "exported_today",
        "output_pairing": Pairing.AL_MEASURED_EXPORTED_ENERGY_TODAY,
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
        "channel_class": VirtualEnergyBattery,
        "value_attribute": "imported_total",
        "output_pairing": Pairing.AL_MEASURED_TOTAL_ENERGY_IMPORTED,
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
        "channel_class": VirtualEnergyBattery,
        "value_attribute": "exported_total",
        "output_pairing": Pairing.AL_MEASURED_TOTAL_ENERGY_EXPORTED,
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
        "channel_class": VirtualEnergyInverter,
        "value_attribute": "current_power",
        "output_pairing": Pairing.AL_MEASURED_CURRENT_POWER_CONSUMED,
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
        "channel_class": VirtualEnergyInverter,
        "value_attribute": "imported_today",
        "output_pairing": Pairing.AL_MEASURED_IMPORTED_ENERGY_TODAY,
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
        "channel_class": VirtualEnergyInverter,
        "value_attribute": "imported_total",
        "output_pairing": Pairing.AL_MEASURED_TOTAL_ENERGY_IMPORTED,
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
        "channel_class": VirtualEnergyTwoWayMeter,
        "value_attribute": "current_power",
        "output_pairing": Pairing.AL_MEASURED_CURRENT_POWER_CONSUMED,
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
        "channel_class": VirtualEnergyTwoWayMeter,
        "value_attribute": "imported_today",
        "output_pairing": Pairing.AL_MEASURED_IMPORTED_ENERGY_TODAY,
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
        "channel_class": VirtualEnergyTwoWayMeter,
        "value_attribute": "exported_today",
        "output_pairing": Pairing.AL_MEASURED_EXPORTED_ENERGY_TODAY,
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
        "channel_class": VirtualEnergyTwoWayMeter,
        "value_attribute": "imported_total",
        "output_pairing": Pairing.AL_MEASURED_TOTAL_ENERGY_IMPORTED,
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
        "channel_class": VirtualEnergyTwoWayMeter,
        "value_attribute": "exported_total",
        "output_pairing": Pairing.AL_MEASURED_TOTAL_ENERGY_EXPORTED,
        "entity_description_kwargs": {
            "device_class": NumberDeviceClass.ENERGY,
            "translation_key": "virtual_energy_two_way_meter_exported_total",
            "native_max_value": 1000000000.0,
            "native_min_value": 0.0,
            "native_step": 1.0,
            "native_unit_of_measurement": UnitOfEnergy.WATT_HOUR,
        },
    },
    "VirtualRoomTemperatureControllerCurrentTemperature": {
        "channel_class": VirtualRoomTemperatureController,
        "value_attribute": "current_temperature",
        "output_pairing": Pairing.AL_MEASURED_TEMPERATURE,
        "entity_description_kwargs": {
            "device_class": NumberDeviceClass.TEMPERATURE,
            "translation_key": "virtual_rtc_current_temperature",
            "native_max_value": 999.9,
            "native_min_value": -999.9,
            "native_step": 0.1,
            "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
        },
    },
    "VirtualRoomTemperatureControllerTargetTemperature": {
        "channel_class": VirtualRoomTemperatureController,
        "value_attribute": "target_temperature",
        "output_pairing": Pairing.AL_SET_POINT_TEMPERATURE,
        "entity_description_kwargs": {
            "device_class": NumberDeviceClass.TEMPERATURE,
            "translation_key": "virtual_rtc_target_temperature",
            "native_max_value": 35.0,
            "native_min_value": 7.0,
            "native_step": 0.5,
            "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
        },
    },
    "VirtualTemperatureSensor": {
        "channel_class": VirtualTemperatureSensor,
        "value_attribute": "temperature",
        "output_pairing": Pairing.AL_OUTDOOR_TEMPERATURE,
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
        "channel_class": VirtualWindSensor,
        "value_attribute": "force",
        "output_pairing": Pairing.AL_WIND_FORCE,
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
        "channel_class": VirtualWindSensor,
        "value_attribute": "speed",
        "output_pairing": Pairing.AL_WIND_SPEED,
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

    def build_entities(get_channels: ChannelGetter) -> list[FreeAtHomeNumberEntity]:
        # Unlike other platforms, skip only the outputs a channel lacks, not
        # unknown values: numbers set the values of virtual devices, so a
        # number must exist before its first value is set.
        return [
            FreeAtHomeNumberEntity(
                channel,
                value_attribute=description.get("value_attribute"),
                entity_description_kwargs={"key": key}
                | description.get("entity_description_kwargs"),
                sysap_serial_number=entry.data[CONF_SERIAL],
                create_subdevices=entry.data[CONF_CREATE_SUBDEVICES],
            )
            for key, description in NUMBER_DESCRIPTIONS.items()
            for channel in get_channels(description.get("channel_class"))
            if _has_output(channel, description.get("output_pairing"))
        ]

    async_setup_platform_entities(hass, entry, async_add_entities, build_entities)


def _has_output(channel: Base, pairing: Pairing) -> bool:
    """Return whether the channel has the output with the pairing."""
    try:
        channel.get_output_by_pairing(pairing)
    except InvalidDeviceChannelPairing:
        return False
    return True


class FreeAtHomeNumberEntity(FreeAtHomeEntity, NumberEntity):
    """Defines a free@home number entity."""

    _attr_should_poll: bool = False

    def __init__(
        self,
        channel: VirtualBrightnessSensor | VirtualTemperatureSensor,
        value_attribute: str,
        entity_description_kwargs: dict[str, Any],
        sysap_serial_number: str,
        create_subdevices: bool,
    ) -> None:
        """Initialize the number."""
        super().__init__()
        self._channel = channel
        self._value_attribute = value_attribute
        self._sysap_serial_number = sysap_serial_number
        self._create_subdevices = create_subdevices

        self.entity_description = NumberEntityDescription(
            has_entity_name=True,
            name=channel.channel_name,
            translation_placeholders={"channel_id": channel.channel_id},
            **entity_description_kwargs,
        )

    async def async_added_to_hass(self) -> None:
        """Run when this entity has been added to HA."""
        await super().async_added_to_hass()
        self._channel.register_callback(
            callback_attribute=self._value_attribute, callback=self.async_write_ha_state
        )

    async def async_will_remove_from_hass(self) -> None:
        """Entity beeing removed from hass."""
        self._channel.remove_callback(
            callback_attribute=self._value_attribute, callback=self.async_write_ha_state
        )

    @property
    def device_info(self) -> AnyDeviceInfo:
        """Information about this entity/device."""
        if self._create_subdevices and self._channel.device.is_multi_device:
            return async_get_sub_device_info(
                self.hass, self.platform.config_entry.entry_id, self._channel
            )

        return DeviceInfo(identifiers={(DOMAIN, self._channel.device_serial)})

    @property
    def native_value(self) -> float | None:
        """Return value of the number."""
        return getattr(self._channel, self._value_attribute)

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._channel.device_serial}_{self._channel.channel_id}_{self.entity_description.key}"

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value.

        This is especially needed as there are devices (virtual) with multiple numbers to set.
        """
        _method_to_call = "set_" + self._value_attribute
        await getattr(self._channel, _method_to_call)(float(value))

    async def async_update(self) -> None:
        """Refresh the channel's values from the SysAP.

        The entity does not poll, so this runs only when the entity is updated
        on request, such as with the homeassistant.update_entity action.
        """
        await self._async_refresh_channel()
