"""Test the script that runs the tests against Home Assistant versions."""

import importlib.util
import io
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any
import urllib.request

import pytest

_SCRIPTS = Path(__file__).parents[1] / ".github" / "scripts"


def _load(name: str) -> ModuleType:
    """Load a script as a module."""
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# The script imports ha_test_matrix from its own directory.
if "ha_test_matrix" not in sys.modules:
    _load("ha_test_matrix")
ha_versions = _load("test_ha_versions")

SHA = "1cc3e51cce06be9c2aedac564b3b13134c661fc6"
COMMIT_URL = "https://api.github.com/repos/home-assistant/core/commits/dev"
PYPROJECT_URL = (
    f"https://raw.githubusercontent.com/home-assistant/core/{SHA}/pyproject.toml"
)
ARCHIVE = f"https://github.com/home-assistant/core/archive/{SHA}.tar.gz"
DEV_ENTRY = {
    "homeassistant": "dev@1cc3e51",
    "python": "3.14.2",
    "plugin": (
        f"pytest-homeassistant @ {ARCHIVE}#subdirectory=packages/pytest-homeassistant"
    ),
    "packages": [f"homeassistant @ {ARCHIVE}"],
}
PAGES = {
    COMMIT_URL: SHA,
    PYPROJECT_URL: '[project]\nrequires-python = ">=3.14.2"',
}


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> list[urllib.request.Request]:
    """Serve GitHub from PAGES and return the requests."""
    requests: list[urllib.request.Request] = []

    def urlopen(request: urllib.request.Request, timeout: float) -> io.BytesIO:
        requests.append(request)
        return io.BytesIO(PAGES[request.full_url].encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return requests


@pytest.fixture
def release_matrix(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, list[str]]]:
    """Replace the release matrix and the dev entry, and return the matrix calls."""
    calls: list[tuple[int, list[str]]] = []

    def build_matrix(count: int, versions: list[str]) -> list[dict[str, Any]]:
        calls.append((count, versions))
        return [{"homeassistant": version} for version in versions or ["2026.11.0"]]

    monkeypatch.setattr(ha_versions, "build_matrix", build_matrix)
    monkeypatch.setattr(ha_versions, "dev_entry", lambda: DEV_ENTRY)
    return calls


def test_dev_entry(github: list[urllib.request.Request]) -> None:
    """Test Home Assistant and its plugin are installed from one dev commit."""
    assert ha_versions.dev_entry() == DEV_ENTRY
    assert [
        (
            request.full_url,
            request.get_header("Accept"),
            request.get_header("User-agent"),
        )
        for request in github
    ] == [
        (COMMIT_URL, "application/vnd.github.sha", "ha-test-versions"),
        (PYPROJECT_URL, None, "ha-test-versions"),
    ]


@pytest.mark.usefixtures("github")
def test_dev_entry_without_python_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test a dev commit without a minimum Python version exits."""
    monkeypatch.setitem(PAGES, PYPROJECT_URL, "[project]")

    with pytest.raises(
        SystemExit,
        match=f"Cannot read the Python version of Home Assistant dev at {SHA}",
    ):
        ha_versions.dev_entry()


@pytest.mark.parametrize(
    ("versions", "calls", "selected"),
    [
        ([], [(7, [])], ["2026.11.0"]),
        (["dev"], [], ["dev@1cc3e51"]),
        (["2026.10", "dev"], [(7, ["2026.10"])], ["2026.10", "dev@1cc3e51"]),
    ],
)
def test_select_matrix(
    release_matrix: list[tuple[int, list[str]]],
    versions: list[str],
    calls: list[tuple[int, list[str]]],
    selected: list[str],
) -> None:
    """Test dev is selected besides the given releases, not the latest ones."""
    matrix = ha_versions.select_matrix(7, versions)

    assert [entry["homeassistant"] for entry in matrix] == selected
    assert release_matrix == calls


@pytest.mark.usefixtures("release_matrix")
def test_main_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test dev runs with Home Assistant from its archive, without the gate."""
    runs: list[tuple[str, list[str], list[str]]] = []

    def uv_run(python: str, packages: list[str], args: list[str], env: dict) -> int:
        runs.append((python, packages, args))
        return 0

    monkeypatch.setattr(ha_versions, "uv_run", uv_run)

    with pytest.raises(SystemExit) as exit_info:
        ha_versions.main(["--ha", "dev"])

    manifest = json.loads(ha_versions.MANIFEST.read_text(encoding="utf-8"))
    assert exit_info.value.code == 0
    assert runs[0][:2] == (
        "3.14.2",
        [
            f"homeassistant @ {ARCHIVE}",
            DEV_ENTRY["plugin"],
            "pytest-cov",
            *manifest["requirements"],
        ],
    )
    assert runs[-1][2] == ["coverage", "report", "--show-missing"]
