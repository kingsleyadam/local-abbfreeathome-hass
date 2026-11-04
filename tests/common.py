"""Test helpers from the installed Home Assistant pytest plugin."""

try:
    from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed
except ImportError:  # Home Assistant without pytest-homeassistant
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        async_fire_time_changed,
    )

__all__ = ["MockConfigEntry", "async_fire_time_changed"]
