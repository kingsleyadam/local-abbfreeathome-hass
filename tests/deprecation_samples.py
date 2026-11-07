"""Tests for test_deprecations.py, which runs them in a separate pytest run.

Two of them log a deprecation and fail by design. The module name does not match
test_*.py, so pytest collects it only when given its path.
"""

import logging

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, callback

_LOGGER = logging.getLogger(__name__)


def test_deprecation_in_test() -> None:
    """Log a deprecation in the test."""
    _LOGGER.warning("The test uses something deprecated")


async def test_deprecation_on_hass_stop(hass: HomeAssistant) -> None:
    """Log a deprecation when the hass fixture is torn down."""

    @callback
    def stop(event: Event) -> None:
        _LOGGER.warning("Stopping uses something deprecated")

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stop)


def test_without_deprecation() -> None:
    """Pass after the tests that logged a deprecation."""
