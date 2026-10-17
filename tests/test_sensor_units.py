"""Tests for sensor unit compatibility across Home Assistant versions."""

from runpy import run_module
from types import SimpleNamespace

import pytest

from homeassistant import const


@pytest.mark.parametrize("modern_units", [False, True])
def test_parts_per_million_compatibility(monkeypatch, modern_units):
    """Prefer the modern enum and fall back only when it is unavailable."""
    monkeypatch.setattr(
        const, "CONCENTRATION_PARTS_PER_MILLION", "legacy_ppm", raising=False
    )
    if modern_units:
        monkeypatch.setattr(
            const,
            "UnitOfRatio",
            SimpleNamespace(PARTS_PER_MILLION="modern_ppm"),
            raising=False,
        )
    else:
        monkeypatch.delattr(const, "UnitOfRatio", raising=False)

    sensor = run_module("custom_components.abbfreeathome_ci.sensor")
    expected_unit = "modern_ppm" if modern_units else "legacy_ppm"

    assert sensor["PARTS_PER_MILLION"] == expected_unit
    assert (
        sensor["SENSOR_DESCRIPTIONS"]["AirQualitySensorCO2"][
            "entity_description_kwargs"
        ]["native_unit_of_measurement"]
        == expected_unit
    )
