"""Test that a logged deprecation fails the test."""

import logging
from pathlib import Path
import subprocess
import sys

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.deprecation import deprecated_function
from homeassistant.helpers.frame import ReportBehavior, report_usage

from .deprecations import DeprecationLog

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_integration_imports_without_deprecation() -> None:
    """Import every module of the integration without logging a deprecation.

    Deprecated constants and enum members, and deprecated properties an entity
    class still provides, are logged once while a module is imported, before
    the first test runs. A fresh interpreter imports the modules again.
    """
    result = subprocess.run(
        [sys.executable, "-m", "tests.deprecations"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


async def test_report_usage_fails_the_test(
    hass: HomeAssistant, deprecation_log: DeprecationLog
) -> None:
    """Fail on a deprecated use of the Home Assistant API it reports."""
    report_usage(
        "uses a deprecated API",
        breaks_in_ha_version="2099.1.0",
        core_behavior=ReportBehavior.LOG,
    )

    with pytest.raises(pytest.fail.Exception, match="uses a deprecated API"):
        deprecation_log.check()


def test_deprecated_function_fails_the_test(deprecation_log: DeprecationLog) -> None:
    """Fail on a call of a deprecated Home Assistant function, only once."""

    @deprecated_function("new_function", breaks_in_ha_version="2099.1.0")
    def old_function() -> None:
        """Do nothing."""

    old_function()

    with pytest.raises(pytest.fail.Exception, match="old_function"):
        deprecation_log.check()
    deprecation_log.check()


@pytest.mark.parametrize(
    ("logger", "level", "message", "deprecation"),
    [
        ("homeassistant.helpers.frame", logging.WARNING, "Detected that ...", True),
        (
            "homeassistant.components.event",
            logging.WARNING,
            "Entity event.door: this will stop working in Home Assistant 2027.4",
            True,
        ),
        (
            "custom_components.abbfreeathome_ci.climate",
            logging.WARNING,
            "FreeAtHomeClimateEntity provides the deprecated current_temperature",
            True,
        ),
        (
            "homeassistant.loader",
            logging.WARNING,
            "We found a custom integration abbfreeathome_ci which has not been tested",
            False,
        ),
        ("homeassistant.helpers.frame", logging.INFO, "Detected that ...", False),
    ],
)
def test_deprecation_warnings(
    deprecation_log: DeprecationLog,
    logger: str,
    level: int,
    message: str,
    deprecation: bool,
) -> None:
    """Collect only the warnings that report a deprecation."""
    logging.getLogger(logger).log(level, message)

    assert bool(deprecation_log.pop()) is deprecation
