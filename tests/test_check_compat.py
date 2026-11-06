"""Test the compatibility marker checker."""

import importlib.util
import json
from pathlib import Path
import sys

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "check_compat",
    Path(__file__).parents[1] / ".github" / "scripts" / "check_compat.py",
)
check_compat = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_compat
_SPEC.loader.exec_module(check_compat)


def _write_repo(
    root: Path, source: str, ha_minimum: str | None, library_pin: str = "3.13.0"
) -> None:
    """Write a minimal repository with one source file."""
    hacs = {"name": "ABB-free@home"}
    if ha_minimum:
        hacs["homeassistant"] = ha_minimum
    (root / "hacs.json").write_text(json.dumps(hacs))
    integration = root / "custom_components" / "abbfreeathome_ci"
    integration.mkdir(parents=True)
    (integration / "manifest.json").write_text(
        json.dumps({"requirements": [f"local-abbfreeathome=={library_pin}"]})
    )
    (integration / "helpers.py").write_text(source)
    # Excluded files may contain example markers.
    (root / "tests").mkdir()
    (root / "tests" / "test_check_compat.py").write_text("# compat: example\n")


def test_scan_text() -> None:
    """Test valid, malformed, and unknown markers, ignoring other comments."""
    markers, problems = check_compat.scan_text(
        "helpers.py",
        """\
    # compat: homeassistant<2026.8 - via_device_id replaced via_device
# compat: local-abbfreeathome<3.14 - new channel API
# compat homeassistant<2026.8 - missing colon
# compat: homeassistant<2026.8
# compat: pytest<9.0 - unknown package
# Legacy suffix kept for backward compatibility.
MARKER = "# compat: in a string is ignored"
""",
    )

    assert markers == [
        check_compat.Marker(
            "helpers.py",
            1,
            "homeassistant",
            "2026.8",
            "via_device_id replaced via_device",
        ),
        check_compat.Marker(
            "helpers.py", 2, "local-abbfreeathome", "3.14", "new channel API"
        ),
    ]
    assert [problem.line for problem in problems] == [3, 4, 5]
    assert "unknown compat package 'pytest'" in problems[2].message


@pytest.mark.parametrize(
    ("minimum", "is_expired"),
    [("2026.7.0", False), ("2026.8.0", True), ("2026.8", True), ("2026.10.1", True)],
)
def test_expired(minimum: str, is_expired: bool) -> None:
    """Test a marker expires once the minimum reaches its version."""
    marker = check_compat.Marker("helpers.py", 1, "homeassistant", "2026.8", "reason")

    problems = check_compat.expired(
        [marker], {"homeassistant": minimum, "local-abbfreeathome": None}
    )

    assert bool(problems) is is_expired


@pytest.mark.parametrize(
    ("minimum", "oldest_tested", "warns"),
    [
        ("2026.5.0", "2026.5.4", False),
        ("2026.5.0", "2026.6.0", True),
        (None, "2026.5.4", True),
    ],
)
def test_minimum_behind_tests(minimum, oldest_tested, warns) -> None:
    """Test the warning when the test matrix moved past the minimum."""
    assert (
        check_compat.minimum_behind_tests(minimum, oldest_tested) is not None
    ) is warns


@pytest.mark.parametrize(
    ("ha_minimum", "library_pin", "exit_code"),
    [
        (None, "3.13.0", 0),
        ("2026.7.0", "3.13.0", 0),
        ("2026.8.0", "3.13.0", 1),
        ("2026.7.0", "3.14.0", 1),
    ],
)
def test_main(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    ha_minimum: str | None,
    library_pin: str,
    exit_code: int,
) -> None:
    """Test markers expire with hacs.json and the manifest library pin."""
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    _write_repo(
        tmp_path,
        "# compat: homeassistant<2026.8 - via_device_id replaced via_device\n"
        "# compat: local-abbfreeathome<3.14 - new channel API\n",
        ha_minimum,
        library_pin,
    )

    assert check_compat.main(["--list"], root=tmp_path) == exit_code

    output = capsys.readouterr().out
    assert (
        "homeassistant<2026.8\n  custom_components/abbfreeathome_ci/helpers.py:1:"
        in (output)
    )
    assert ("error:" in output) is bool(exit_code)


def test_main_minimum_override(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test --minimum previews markers expiring at a Home Assistant version."""
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    _write_repo(tmp_path, "# compat: homeassistant<2026.8 - reason\n", "2026.5.0")

    assert check_compat.main(["--minimum", "2026.8"], root=tmp_path) == 1
    assert "the minimum is 2026.8" in capsys.readouterr().out


def test_main_github_annotations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test problems are GitHub annotations in GitHub Actions."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    _write_repo(tmp_path, "# compat: homeassistant<2026.5 - reason\n", "2026.5.0")

    assert check_compat.main(["--oldest-tested", "2026.6.1"], root=tmp_path) == 1

    output = capsys.readouterr().out
    assert output.startswith("::warning file=hacs.json,line=1::")
    assert "::error file=custom_components/abbfreeathome_ci/helpers.py,line=1::" in (
        output
    )
