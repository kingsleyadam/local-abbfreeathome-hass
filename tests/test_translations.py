"""Test the translations of the ABB-free@home integration.

The tests read the source instead of running it, so keys built at runtime are
not checked. hassfest only validates the format of the files.
"""

import ast
import json
from pathlib import Path

import pytest

from custom_components.abbfreeathome_ci import PLATFORMS

COMPONENT_PATH = Path("custom_components/abbfreeathome_ci")
TRANSLATIONS = ("translations/en.json", "translations/de.json")

# Abort reasons the Home Assistant config flow helpers use on their own.
IMPLICIT_ABORT_REASONS = {
    "already_configured",
    "already_in_progress",
    "reconfigure_successful",
}

# Known gaps, to be fixed separately. The tests fail once a gap is fixed, so
# remove its entry together with the fix.
UNTRANSLATED_ABORT_REASONS = {"invalid_api", "invalid_settings", "not_ipv4address"}
UNRESOLVED_REFERENCES = {
    "translations/en.json": {
        "entity.event.staircase_light_sensor.state_attributes.event_type.state.off",
        "entity.event.staircase_light_sensor.state_attributes.event_type.state.on",
    },
}


def _load(name: str) -> dict:
    """Load one of the integration's json files."""
    return json.loads((COMPONENT_PATH / name).read_text(encoding="utf-8"))


def _flatten(data: dict, prefix: str = "") -> dict[str, object]:
    """Return every key of a nested dict as a dotted path with its value."""
    flat = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        flat[path] = value
        if isinstance(value, dict):
            flat |= _flatten(value, path)
    return flat


def _string_constants(module: str, name: str) -> set[str]:
    """Return the string literals a module uses as `name`.

    Covers keyword arguments and dict entries named `name`, item assignments
    to `name[...]`, and assignments to `_attr_<name>`.
    """
    tree = ast.parse((COMPONENT_PATH / f"{module}.py").read_text(encoding="utf-8"))
    values = []
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == name:
            values.append(node.value)
        elif isinstance(node, ast.Dict):
            values.extend(
                value
                for key, value in zip(node.keys, node.values, strict=True)
                if isinstance(key, ast.Constant) and key.value == name
            )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(
                (isinstance(target, ast.Name) and target.id == f"_attr_{name}")
                or (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == name
                )
                for target in targets
            ):
                values.append(node.value)

    return {
        value.value
        for value in values
        if isinstance(value, ast.Constant) and isinstance(value.value, str)
    }


@pytest.fixture
def strings() -> dict:
    """Return the english strings."""
    return _load("strings.json")


@pytest.mark.parametrize("name", TRANSLATIONS)
def test_translations_have_the_same_keys(strings, name) -> None:
    """Test every translation file has exactly the keys of strings.json.

    Home Assistant only loads translations/*.json for custom integrations and
    nothing generates them, so a missing key shows as a raw key to users.
    """
    assert set(_flatten(_load(name))) == set(_flatten(strings))


@pytest.mark.parametrize("name", TRANSLATIONS)
def test_translations_have_no_references(name) -> None:
    """Test translation files contain text, not [%key:...%] references.

    Only strings.json may use references; Home Assistant does not resolve them
    in the translation files of custom integrations.
    """
    references = {
        path
        for path, value in _flatten(_load(name)).items()
        if isinstance(value, str) and "[%key:" in value
    }

    assert references == UNRESOLVED_REFERENCES.get(name, set())


def test_config_flow_steps_are_translated(strings) -> None:
    """Test every config flow step has strings."""
    step_ids = _string_constants("config_flow", "step_id")

    assert step_ids
    assert step_ids <= set(strings["config"]["step"])


def test_config_flow_errors_are_translated(strings) -> None:
    """Test every config flow error has a message."""
    errors = _string_constants("config_flow", "errors")

    assert errors
    assert errors <= set(strings["config"]["error"])


def test_config_flow_abort_reasons_are_translated(strings) -> None:
    """Test every config flow abort reason has a message."""
    reasons = _string_constants("config_flow", "reason") | IMPLICIT_ABORT_REASONS

    assert reasons - set(strings["config"]["abort"]) == UNTRANSLATED_ABORT_REASONS


@pytest.mark.parametrize("platform", PLATFORMS)
def test_entity_translation_keys_are_translated(strings, platform) -> None:
    """Test every entity translation key of a platform has strings."""
    translation_keys = _string_constants(platform.value, "translation_key")

    assert translation_keys <= set(strings["entity"].get(platform.value, {}))


def test_service_exceptions_are_translated(strings) -> None:
    """Test every exception raised with a translation key has a message."""
    translation_keys = _string_constants("__init__", "translation_key")

    assert translation_keys
    assert translation_keys <= set(strings["exceptions"])
