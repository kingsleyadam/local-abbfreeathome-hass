"""Create ABB-free@home event entities."""

# ABB_RESYNC_GUARD_PATCH_v3 — flood-detection wrapper to suppress
# spurious "button press" events when local-abbfreeathome resyncs all
# channel state attributes after a SysAP WebSocket reconnect.
#
# Why: abbfreeathome library fires the registered state-callback for
# every channel during initial sync (no "is_resync" flag). HA-side
# EventEntity then publishes state_changed for every event.* sensor,
# which fires every `trigger: state` automation in the house.
#
# v3 strategy: track recent (timestamp, entity_id) pairs in a sliding
# window. Declare a SysAP resync flood when EITHER:
#   (a) more than 2 distinct entity_ids fired within the window, OR
#   (b) more than 1 distinct entity AND >= 10 total callbacks fired.
# On detection, enter a cooldown during which every callback is
# silently dropped. Real human presses (1–2 different keys within 2s,
# each producing 1 press + 1 release on the same entity) stay under
# both thresholds and pass through. SysAP reconnect resync (50+
# distinct entities, ~100 callbacks within 20s) triggers (a) and (b)
# on the second–third callback and the rest is cooled down.
#
# History:
#   v1 — raw count threshold (>6 callbacks/2s). Let first 6 through;
#        one randomly hit ch0001 of a real switch and toggled the
#        kitchen chandelier.
#   v2 — unique > 1 distinct entity in window. Triggered on the very
#        second entity, leaving only a single callback slip. But this
#        misfired when a human pressed two different keys within 2s
#        of each other (legitimate user input was suppressed).
#   v3 — unique > 2 OR (unique > 1 AND total >= 10). Tolerant of
#        legitimate two-key sequences while still catching reconnect.

import time
from collections import deque
from typing import Any

from abbfreeathome import FreeAtHome
from abbfreeathome.channels.blind_sensor import BlindSensor, BlindSensorState
from abbfreeathome.channels.des_door_ringing_sensor import DesDoorRingingSensor
from abbfreeathome.channels.force_on_off_sensor import (
    ForceOnOffSensor,
    ForceOnOffSensorState,
)
from abbfreeathome.channels.switch_sensor import (
    DimmingSensor,
    DimmingSensorState,
    SwitchSensor,
    SwitchSensorState,
)
from abbfreeathome.channels.virtual.virtual_room_temperature_controller import (
    VirtualRoomTemperatureController,
)
from abbfreeathome.channels.virtual.virtual_switch_actuator import VirtualSwitchActuator

from homeassistant.components.event import (
    EventDeviceClass,
    EventEntity,
    EventEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CREATE_SUBDEVICES, CONF_SERIAL, DOMAIN, MANUFACTURER

import logging

_LOGGER = logging.getLogger(__name__)

EVENT_DESCRIPTIONS = {
    "EventBlindSensorState": {
        "channel_class": BlindSensor,
        "event_type_callback": lambda state: state,
        "state_attribute": "state",
        "entity_description_kwargs": {
            "device_class": EventDeviceClass.BUTTON,
            "event_types": [state.name for state in BlindSensorState],
            "translation_key": "blind_sensor",
        },
    },
    "EventDesDoorRingingSensorActivated": {
        "channel_class": DesDoorRingingSensor,
        "event_type_callback": lambda: "activated",
        "state_attribute": "",
        "entity_description_kwargs": {
            "device_class": EventDeviceClass.BUTTON,
            "event_types": ["activated"],
            "translation_key": "des_door_ringing_sensor",
        },
    },
    "EventDimmingSensorState": {
        "channel_class": DimmingSensor,
        "event_type_callback": lambda state: state,
        "state_attribute": "state",
        "entity_description_kwargs": {
            "device_class": EventDeviceClass.BUTTON,
            "event_types": list(
                set(
                    [state.name for state in SwitchSensorState]
                    + [state.name for state in DimmingSensorState]
                )
            ),
            "translation_key": "dimming_sensor",
        },
    },
    "EventForceOnOffSensorOnOff": {
        "channel_class": ForceOnOffSensor,
        "event_type_callback": lambda state: state,
        "state_attribute": "state",
        "entity_description_kwargs": {
            "device_class": EventDeviceClass.BUTTON,
            "event_types": [state.name for state in ForceOnOffSensorState],
            "translation_key": "force_on_off_sensor",
        },
    },
    "EventSwitchSensorOnOff": {
        "channel_class": SwitchSensor,
        "event_type_callback": lambda state: state,
        "state_attribute": "state",
        "entity_description_kwargs": {
            "device_class": EventDeviceClass.BUTTON,
            "event_types": [state.name for state in SwitchSensorState],
            "translation_key": "switch_sensor",
        },
    },
    "EventVirtualRoomTemperatureControllerOnOff": {
        "channel_class": VirtualRoomTemperatureController,
        "event_type_callback": lambda requested_state: (
            "On" if requested_state else "Off"
        ),
        "state_attribute": "requested_state",
        "entity_description_kwargs": {
            "device_class": EventDeviceClass.BUTTON,
            "event_types": ["On", "Off"],
            "translation_key": "virtual_room_temperature_controller_onoff",
        },
    },
    "EventVirtualRoomTemperatureControllerEcoOnOff": {
        "channel_class": VirtualRoomTemperatureController,
        "event_type_callback": lambda requested_eco_mode: (
            "On" if requested_eco_mode else "Off"
        ),
        "state_attribute": "requested_eco_mode",
        "entity_description_kwargs": {
            "device_class": EventDeviceClass.BUTTON,
            "event_types": ["On", "Off"],
            "translation_key": "virtual_room_temperature_controller_ecoonoff",
        },
    },
    "EventVirtualRoomTemperatureControllerTargetTemperature": {
        "channel_class": VirtualRoomTemperatureController,
        "event_type_callback": lambda requested_target_temperature: (
            "requested_target_temperature"
        ),
        "state_attribute": "requested_target_temperature",
        "entity_description_kwargs": {
            "event_types": ["requested_target_temperature"],
            "translation_key": "virtual_room_temperature_controller_target_temperature",
        },
        "extra_data": "requested_target_temperature",
    },
    "EventVirtualSwitchActuatorOnOff": {
        "channel_class": VirtualSwitchActuator,
        "event_type_callback": lambda requested_state: (
            "On" if requested_state else "Off"
        ),
        "state_attribute": "requested_state",
        "entity_description_kwargs": {
            "device_class": EventDeviceClass.BUTTON,
            "event_types": ["On", "Off"],
            "translation_key": "virtual_switch_actuator_onoff",
        },
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up event entities."""
    free_at_home: FreeAtHome = hass.data[DOMAIN][entry.entry_id]

    for key, description in EVENT_DESCRIPTIONS.items():
        async_add_entities(
            FreeAtHomeEventEntity(
                channel,
                state_attribute=description.get("state_attribute"),
                entity_description_kwargs={"key": key}
                | description.get("entity_description_kwargs"),
                sysap_serial_number=entry.data[CONF_SERIAL],
                create_subdevices=entry.data[CONF_CREATE_SUBDEVICES],
                event_type_callback=description.get("event_type_callback"),
                extra_data=description.get("extra_data")
                if "extra_data" in description
                else None,
            )
            for channel in free_at_home.get_channels_by_class(
                channel_class=description.get("channel_class")
            )
        )


class FreeAtHomeEventEntity(EventEntity):
    """free@home Event Entity."""

    # === ABB_RESYNC_GUARD_PATCH_v3 ===
    # Sliding-window log of recent (monotonic_timestamp, entity_id)
    # across ALL FreeAtHomeEventEntity instances.
    _GUARD_RECENT: deque = deque(maxlen=400)
    # Window length for the flood detector.
    _GUARD_WINDOW_S = 2.0
    # Flood detection thresholds (see header comment for rationale):
    #   unique > _GUARD_UNIQUE_HARD                      -> flood
    #   unique > 1 AND total >= _GUARD_TOTAL_DENSITY     -> flood
    _GUARD_UNIQUE_HARD = 2
    _GUARD_TOTAL_DENSITY = 10
    # When a flood is detected, suppress everything for this many
    # seconds so the late re-publish wave is also caught.
    _GUARD_COOLDOWN_S = 30.0
    _GUARD_COOLDOWN_UNTIL = 0.0
    # Throttle for the "suppressed" warning log line.
    _GUARD_LAST_WARN = 0.0
    _GUARD_WARN_INTERVAL_S = 10.0
    # === /ABB_RESYNC_GUARD_PATCH_v3 ===

    def __init__(
        self,
        channel: BlindSensor
        | DesDoorRingingSensor
        | DimmingSensor
        | ForceOnOffSensor
        | SwitchSensor
        | VirtualSwitchActuator,
        state_attribute: str,
        entity_description_kwargs: dict[str, Any],
        sysap_serial_number: str,
        create_subdevices: bool,
        event_type_callback: callback,
        extra_data: str | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__()
        self._channel = channel
        self._state_attribute = state_attribute
        self._sysap_serial_number = sysap_serial_number
        self._create_subdevices = create_subdevices
        self._event_type_callback = event_type_callback
        self._extra_data = extra_data

        self.entity_description = EventEntityDescription(
            has_entity_name=True,
            name=channel.channel_name,
            translation_placeholders={"channel_id": channel.channel_id},
            **entity_description_kwargs,
        )

    @callback
    def _async_handle_event(self) -> None:
        """Handle the event."""

        # === ABB_RESYNC_GUARD_PATCH_v3 ===
        cls = FreeAtHomeEventEntity
        now = time.monotonic()

        # 1) If we are inside a post-flood cooldown, drop unconditionally.
        if now < cls._GUARD_COOLDOWN_UNTIL:
            if now - cls._GUARD_LAST_WARN > cls._GUARD_WARN_INTERVAL_S:
                cls._GUARD_LAST_WARN = now
                _LOGGER.warning(
                    "ABB resync flood suppressed (cooldown %.0fs remaining): %s",
                    cls._GUARD_COOLDOWN_UNTIL - now,
                    self.entity_id,
                )
            return

        # 2) Maintain the sliding window of (ts, entity_id).
        recent = cls._GUARD_RECENT
        cutoff = now - cls._GUARD_WINDOW_S
        while recent and recent[0][0] < cutoff:
            recent.popleft()
        recent.append((now, self.entity_id))

        # 3) Flood detector (see header comment).
        unique = {eid for _, eid in recent}
        total = len(recent)
        if (
            len(unique) > cls._GUARD_UNIQUE_HARD
            or (len(unique) > 1 and total >= cls._GUARD_TOTAL_DENSITY)
        ):
            cls._GUARD_COOLDOWN_UNTIL = now + cls._GUARD_COOLDOWN_S
            cls._GUARD_LAST_WARN = now
            _LOGGER.warning(
                "ABB resync flood detected: %d distinct entities, "
                "%d total callbacks in %.1fs (this=%s). Cooldown %.0fs.",
                len(unique),
                total,
                cls._GUARD_WINDOW_S,
                self.entity_id,
                cls._GUARD_COOLDOWN_S,
            )
            return
        # === /ABB_RESYNC_GUARD_PATCH_v3 ===

        if hasattr(self._channel, self._state_attribute):
            event_type = self._event_type_callback(
                getattr(self._channel, self._state_attribute)
            )
        else:
            event_type = self._event_type_callback()

        _extra_data = None

        if self._extra_data and hasattr(self._channel, self._extra_data):
            _extra_data = getattr(self._channel, self._extra_data)

        self._trigger_event(event_type, {"extra_data": _extra_data})
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Entity being added to hass."""
        if len(self._state_attribute) > 0:
            self._channel.register_callback(
                callback_attribute=self._state_attribute,
                callback=self._async_handle_event,
            )
        else:
            self._channel.register_callback(
                callback_attribute="state", callback=self._async_handle_event
            )

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        if len(self._state_attribute) > 0:
            self._channel.remove_callback(
                callback_attribute=self._state_attribute,
                callback=self._async_handle_event,
            )
        else:
            self._channel.remove_callback(
                callback_attribute="state", callback=self._async_handle_event
            )

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        if self._create_subdevices and self._channel.device.is_multi_device:
            return DeviceInfo(
                identifiers={
                    (
                        DOMAIN,
                        f"{self._channel.device_serial}_{self._channel.channel_id}",
                    )
                },
                name=f"{self._channel.device_name} ({self._channel.channel_id})",
                manufacturer=MANUFACTURER,
                serial_number=f"{self._channel.device_serial}_{self._channel.channel_id}",
                hw_version=f"{self._channel.device.device_id} (sub)",
                suggested_area=self._channel.room_name,
                via_device=(DOMAIN, self._channel.device_serial),
            )

        return DeviceInfo(identifiers={(DOMAIN, self._channel.device_serial)})

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self._channel.device_serial}_{self._channel.channel_id}_{self.entity_description.key}"
