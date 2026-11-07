"""Global fixtures for ABB-free@home integration tests."""

from collections.abc import Generator
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.abbfreeathome_ci.const import DOMAIN

from .common import MockConfigEntry
from .deprecations import DeprecationLog

_DEPRECATION_LOG = DeprecationLog()


def pytest_configure(config: pytest.Config) -> None:
    """Collect the deprecations logged while the tests run."""
    logging.getLogger().addHandler(_DEPRECATION_LOG)


def pytest_unconfigure(config: pytest.Config) -> None:
    """Stop collecting deprecations."""
    logging.getLogger().removeHandler(_DEPRECATION_LOG)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item: pytest.Item) -> Generator[None]:
    """Forget the deprecations logged before the test, such as on import.

    A test in test_deprecations.py checks those of the integration's imports.
    """
    _DEPRECATION_LOG.pop()
    return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item: pytest.Item) -> Generator[None]:
    """Fail the test if a deprecation was logged during it.

    A hook instead of a fixture also covers the teardown of all fixtures,
    including the hass fixture.
    """
    yield
    _DEPRECATION_LOG.check()


@pytest.fixture
def deprecation_log() -> DeprecationLog:
    """Return the deprecations logged, for a test expecting one to pop() it."""
    return _DEPRECATION_LOG


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    return


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Mock setting up a config entry."""
    with patch(
        "custom_components.abbfreeathome_ci.async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup


@pytest.fixture
def mock_free_at_home_settings():
    """Mock FreeAtHomeSettings class."""
    with patch(
        "custom_components.abbfreeathome_ci.config_flow.FreeAtHomeSettings"
    ) as mock_settings:
        settings_instance = MagicMock()
        settings_instance.load = AsyncMock()
        settings_instance.has_api_support = True
        settings_instance.serial_number = "TEST123456"
        settings_instance.name = "Test SysAP"
        settings_instance.version = "3.0.0"
        mock_settings.return_value = settings_instance
        yield settings_instance


@pytest.fixture
def mock_free_at_home_api():
    """Mock FreeAtHomeApi class."""
    with patch(
        "custom_components.abbfreeathome_ci.config_flow.FreeAtHomeApi"
    ) as mock_api:
        api_instance = MagicMock()
        api_instance.get_sysap = AsyncMock()
        mock_api.return_value = api_instance
        yield api_instance


@pytest.fixture
def mock_config_entry():
    """Mock a config entry."""
    return MockConfigEntry(
        version=1,
        minor_version=6,
        domain=DOMAIN,
        title="Test SysAP (TEST123456)",
        data={
            "serial": "TEST123456",
            "name": "Test SysAP",
            "host": "http://192.168.1.100",
            "username": "installer",
            "password": "test_password",
            "include_orphan_channels": False,
            "include_virtual_devices": False,
            "create_subdevices": False,
            "create_unresponsive_repairs": False,
            "ssl_cert_file_path": None,
            "verify_ssl": False,
        },
        source="user",
        unique_id="TEST123456",
    )
