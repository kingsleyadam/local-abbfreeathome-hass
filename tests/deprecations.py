"""Find logged deprecations, so that tests fail before the deprecated code breaks.

Run as `python -m tests.deprecations` to import every module of the integration
in a fresh interpreter, which fails on deprecations logged only while importing.
"""

import importlib
import logging
import pkgutil
import sys

import pytest

# Not imported from the integration, which must be imported only after the log
# is set up.
INTEGRATION = "custom_components.abbfreeathome_ci"

# Home Assistant reports deprecated or incorrect use of its API with
# report_usage(), which logs to this logger.
REPORT_USAGE_LOGGER = "homeassistant.helpers.frame"

# Other deprecation warnings say so or name the release that breaks the code.
DEPRECATION_PHRASES = ("deprecated", "will stop working in home assistant")


def is_deprecation(record: logging.LogRecord) -> bool:
    """Return whether a log record reports a deprecation."""
    if record.name == REPORT_USAGE_LOGGER:
        return True
    message = record.getMessage().lower()
    return any(phrase in message for phrase in DEPRECATION_PHRASES)


class DeprecationLog(logging.Handler):
    """Collect the deprecation warnings logged while it is a handler."""

    def __init__(self) -> None:
        """Initialize the log for warnings and above."""
        super().__init__(logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Keep the record if it reports a deprecation."""
        if is_deprecation(record):
            self.records.append(record)

    def pop(self) -> list[logging.LogRecord]:
        """Return and forget the collected records."""
        with self.lock:
            records, self.records = self.records, []
        return records

    def pop_report(self) -> str:
        """Return a report of the collected records, if any, and forget them."""
        messages = dict.fromkeys(
            f"{record.name} logged a deprecation: {record.getMessage()}"
            for record in self.pop()
        )
        return "\n".join(messages)

    def check(self) -> None:
        """Fail the current test if deprecations were logged, and forget them."""
        if report := self.pop_report():
            pytest.fail(report, pytrace=False)


def main() -> None:
    """Import every module of the integration and fail on deprecations."""
    # Imported first as in Home Assistant, whose package aliases modules such
    # as voluptuous before integrations import them.
    importlib.import_module("homeassistant")
    log = DeprecationLog()
    logging.getLogger().addHandler(log)
    package = importlib.import_module(INTEGRATION)
    for module in pkgutil.iter_modules(package.__path__):
        importlib.import_module(f"{INTEGRATION}.{module.name}")
    sys.exit(log.pop_report() or None)


if __name__ == "__main__":
    main()
