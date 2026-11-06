"""Test helpers from the installed Home Assistant pytest plugin."""

# compat: homeassistant<2026.11 - pytest-homeassistant replaced pytest-homeassistant-custom-component
try:
    from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed
except ImportError:
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        async_fire_time_changed,
    )

__all__ = ["MockConfigEntry", "async_fire_time_changed"]
