"""Test the Home Assistant test matrix builder."""

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "ha_test_matrix",
    Path(__file__).parents[1] / ".github" / "scripts" / "ha_test_matrix.py",
)
ha_test_matrix = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = ha_test_matrix
_SPEC.loader.exec_module(ha_test_matrix)


def _files(
    requires_python: str = ">=3.14.2", *, yanked: bool = False
) -> list[dict[str, Any]]:
    """Return the files of a PyPI release."""
    return [{"requires_python": requires_python, "yanked": yanked}]


def _entry(version: str) -> dict[str, str]:
    """Return the matrix entry of a release tested with `pytest-homeassistant`."""
    return {
        "homeassistant": version,
        "python": "3.14.2",
        "plugin": f"pytest-homeassistant=={version}",
    }


@pytest.fixture
def pypi(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, Any]]:
    """Serve PyPI metadata from a dictionary while 2026.12 is in beta."""
    metadata = {
        "homeassistant": {
            "releases": {
                "2026.10.0": _files(">=3.13.2"),
                "2026.10.4": _files(">=3.13.2"),
                "2026.11.0b6": _files(),
                "2026.11.0": _files(),
                "2026.11.1": _files(yanked=True),
                "2026.12.0b0": _files(),
                "2026.12.0b1": _files(),
                "2026.12.0b2": [],
            }
        },
        "pytest-homeassistant": {
            "releases": {
                "2026.11.0b6": _files(),
                "2026.11.0": _files(),
                "2026.12.0b0": _files(),
            }
        },
        "pytest-homeassistant-custom-component": {
            "releases": {"0.13.375": _files(">=3.13.2")}
        },
        "pytest-homeassistant-custom-component/0.13.375": {
            "info": {"requires_dist": ["homeassistant==2026.10.4", "pytest==9.0.0"]}
        },
    }
    monkeypatch.setattr(
        ha_test_matrix,
        "fetch",
        lambda package, version=None: metadata[
            f"{package}/{version}" if version else package
        ],
    )
    return metadata


def test_version_key() -> None:
    """Test betas sort by number and before the release they lead up to."""
    versions = ["2026.12.0", "2026.12.0b10", "2026.11.1", "2026.12.0b2"]

    assert sorted(versions, key=ha_test_matrix.version_key) == [
        "2026.11.1",
        "2026.12.0b2",
        "2026.12.0b10",
        "2026.12.0",
    ]


@pytest.mark.usefixtures("pypi")
def test_build_matrix() -> None:
    """Test the latest minor releases leave out betas and yanked releases."""
    assert ha_test_matrix.build_matrix(2) == [
        _entry("2026.11.0"),
        {
            "homeassistant": "2026.10.4",
            "python": "3.13.2",
            "plugin": "pytest-homeassistant-custom-component==0.13.375",
        },
    ]


@pytest.mark.usefixtures("pypi")
@pytest.mark.parametrize(
    ("spec", "version"),
    [
        ("2026.11", "2026.11.0"),
        ("2026.11.0b6", "2026.11.0b6"),
        ("2026.12", "2026.12.0b0"),
    ],
)
def test_build_matrix_versions(spec: str, version: str) -> None:
    """Test given versions match betas only while their release is not out."""
    assert ha_test_matrix.build_matrix(7, [spec]) == [_entry(version)]


@pytest.mark.usefixtures("pypi")
@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ("2026.12.0", "No Home Assistant release matches 2026.12.0"),
        ("2026.12.0b1", "No pytest plugin found for Home Assistant 2026.12.0b1"),
    ],
)
def test_build_matrix_versions_unavailable(spec: str, message: str) -> None:
    """Test a version without a release or pytest plugin exits."""
    with pytest.raises(SystemExit, match=message):
        ha_test_matrix.build_matrix(7, [spec])


def test_beta_matrix(pypi: dict[str, dict[str, Any]]) -> None:
    """Test the newest beta of an upcoming release is selected."""
    pypi["pytest-homeassistant"]["releases"]["2026.12.0b1"] = _files()

    assert ha_test_matrix.beta_matrix() == [_entry("2026.12.0b1")]


@pytest.mark.usefixtures("pypi")
def test_beta_matrix_waits_for_plugin(capsys: pytest.CaptureFixture[str]) -> None:
    """Test the newest beta is not selected before its pytest plugin exists."""
    assert ha_test_matrix.beta_matrix() == []
    assert "No pytest plugin for Home Assistant 2026.12.0b1 yet" in (
        capsys.readouterr().err
    )


def test_beta_matrix_after_release(pypi: dict[str, dict[str, Any]]) -> None:
    """Test no beta is selected once its release is out."""
    pypi["homeassistant"]["releases"]["2026.12.0"] = _files()

    assert ha_test_matrix.beta_matrix() == []


def test_main(
    pypi: dict[str, dict[str, Any]],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test --beta prints the matrix and writes it to the step output."""
    pypi["pytest-homeassistant"]["releases"]["2026.12.0b1"] = _files()
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    ha_test_matrix.main(["--beta"])

    matrix = [_entry("2026.12.0b1")]
    assert json.loads(capsys.readouterr().out) == matrix
    assert output.read_text() == f"matrix={json.dumps(matrix)}\n"


@pytest.mark.usefixtures("pypi")
def test_main_ha_excludes_beta() -> None:
    """Test --ha and --beta cannot be combined."""
    with pytest.raises(SystemExit):
        ha_test_matrix.main(["--ha", "2026.11", "--beta"])
