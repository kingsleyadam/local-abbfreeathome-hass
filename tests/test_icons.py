"""Test the icon translations of the ABB-free@home integration."""

import json
from pathlib import Path

import pytest

COMPONENT_PATH = Path("custom_components/abbfreeathome_ci")


def _load(name: str) -> dict:
    """Load one of the integration's json files."""
    return json.loads((COMPONENT_PATH / name).read_text(encoding="utf-8"))


@pytest.fixture
def icons() -> dict:
    """Return the icon translations."""
    return _load("icons.json")


@pytest.fixture
def strings() -> dict:
    """Return the english strings."""
    return _load("strings.json")


def test_icons_only_use_known_translation_keys(icons, strings) -> None:
    """Test every icon belongs to a translation key the integration really uses.

    An icon under an unknown key is silently ignored by Home Assistant, so a
    typo or a renamed key would go unnoticed without this test.
    """
    unknown = [
        f"{platform}.{key}"
        for platform, keys in icons["entity"].items()
        for key in keys
        if key not in strings["entity"].get(platform, {})
    ]

    assert not unknown


def test_icons_are_material_design_icons(icons) -> None:
    """Test every icon is a mdi icon, the only set Home Assistant ships."""
    for keys in icons["entity"].values():
        for entry in keys.values():
            for icon in [entry["default"], *entry.get("state", {}).values()]:
                assert icon.startswith("mdi:"), icon
                assert icon == icon.lower().strip()


def test_icon_states_exist_in_the_strings(icons, strings) -> None:
    """Test state icons of enum entities match the translated states.

    Binary sensors, switches and valves carry fixed states that are not listed
    in strings.json, so only the keys that do declare states are checked.
    """
    for platform, keys in icons["entity"].items():
        for key, entry in keys.items():
            _states = strings["entity"].get(platform, {}).get(key, {}).get("state")
            if not _states:
                continue

            assert set(entry.get("state", {})) <= set(_states), f"{platform}.{key}"


def test_every_icon_entry_has_a_default(icons) -> None:
    """Test no entry relies on state icons alone.

    Without a default an entity would fall back to the domain icon whenever it
    is in a state the entry does not name, for example while unavailable.
    """
    for platform, keys in icons["entity"].items():
        for key, entry in keys.items():
            assert "default" in entry, f"{platform}.{key}"
