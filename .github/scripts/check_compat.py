"""Check the compatibility markers against the minimum supported versions.

Code that exists only to support older Home Assistant or library versions is
marked with a full-line comment at the top of the block to delete:

    # compat: homeassistant<2026.8 - via_device_id replaced via_device

The block is needed only while the minimum supported version is below the
marker's version. The minimum Home Assistant version is `homeassistant` in
`hacs.json`; the minimum library version is its pin in `manifest.json`.
Expired and malformed markers are errors.

Usage:
    python .github/scripts/check_compat.py
    python .github/scripts/check_compat.py --list
    python .github/scripts/check_compat.py --minimum 2026.8
    python .github/scripts/check_compat.py --oldest-tested 2026.6.3
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = ("custom_components", "tests", ".github/scripts")
# Contain example markers in strings and docstrings.
EXCLUDE = (".github/scripts/check_compat.py", "tests/test_check_compat.py")
HACS_JSON = "hacs.json"
MANIFEST_JSON = "custom_components/abbfreeathome_ci/manifest.json"

HOMEASSISTANT = "homeassistant"
LIBRARY = "local-abbfreeathome"
PACKAGES = (HOMEASSISTANT, LIBRARY)

CANDIDATE = re.compile(r"^\s*#\s*compat\b", re.IGNORECASE)
MARKER = re.compile(
    r"^\s*# compat: (?P<package>[a-z0-9-]+)<(?P<version>\d+(?:\.\d+){1,2})"
    r" - (?P<reason>\S.*)$"
)
LIBRARY_PIN = re.compile(rf"^{LIBRARY}==(?P<version>\d+(?:\.\d+)*)$")


@dataclass(frozen=True)
class Marker:
    """A compatibility marker in a source file."""

    path: str
    line: int
    package: str
    version: str
    reason: str


@dataclass(frozen=True)
class Problem:
    """A problem found in a source file."""

    path: str
    line: int
    message: str


def version_key(version: str) -> tuple[int, ...]:
    """Return a comparable key for a version, padding missing parts with 0."""
    parts = [int(part) for part in version.split(".")[:3]]
    return (*parts, *[0] * (3 - len(parts)))


def scan_text(path: str, text: str) -> tuple[list[Marker], list[Problem]]:
    """Return the markers and malformed markers in a file's text."""
    markers: list[Marker] = []
    problems: list[Problem] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not CANDIDATE.match(line):
            continue
        match = MARKER.match(line)
        if match is None:
            problems.append(
                Problem(
                    path,
                    line_number,
                    "malformed compat marker, expected "
                    "'# compat: <package><<version> - <reason>'",
                )
            )
        elif match["package"] not in PACKAGES:
            problems.append(
                Problem(
                    path,
                    line_number,
                    f"unknown compat package {match['package']!r}, "
                    f"expected one of {', '.join(PACKAGES)}",
                )
            )
        else:
            markers.append(
                Marker(
                    path,
                    line_number,
                    match["package"],
                    match["version"],
                    match["reason"].strip(),
                )
            )
    return markers, problems


def scan(root: Path) -> tuple[list[Marker], list[Problem]]:
    """Return the markers and malformed markers of all scanned files."""
    markers: list[Marker] = []
    problems: list[Problem] = []
    for scan_dir in SCAN_DIRS:
        for file in sorted((root / scan_dir).rglob("*.py")):
            path = file.relative_to(root).as_posix()
            if path in EXCLUDE:
                continue
            file_markers, file_problems = scan_text(
                path, file.read_text(encoding="utf-8")
            )
            markers.extend(file_markers)
            problems.extend(file_problems)
    return markers, problems


def minimum_versions(root: Path) -> dict[str, str | None]:
    """Return the minimum supported version of each package, if set."""
    hacs = json.loads((root / HACS_JSON).read_text(encoding="utf-8"))
    manifest = json.loads((root / MANIFEST_JSON).read_text(encoding="utf-8"))
    library = next(
        (
            match["version"]
            for requirement in manifest.get("requirements", [])
            if (match := LIBRARY_PIN.match(requirement))
        ),
        None,
    )
    return {HOMEASSISTANT: hacs.get(HOMEASSISTANT), LIBRARY: library}


def expired(markers: list[Marker], minimums: dict[str, str | None]) -> list[Problem]:
    """Return a problem for each marker the minimum version has reached."""
    return [
        Problem(
            marker.path,
            marker.line,
            f"{marker.package}<{marker.version} is no longer needed, the minimum "
            f"is {minimum}; remove the compatibility code: {marker.reason}",
        )
        for marker in markers
        if (minimum := minimums[marker.package]) is not None
        and version_key(minimum) >= version_key(marker.version)
    ]


def minimum_behind_tests(minimum: str | None, oldest_tested: str) -> str | None:
    """Return a warning if the oldest tested minor is newer than the minimum."""
    if minimum is None:
        return (
            f"{HACS_JSON} sets no minimum Home Assistant version; "
            f"the oldest tested version is {oldest_tested}"
        )
    if version_key(oldest_tested)[:2] > version_key(minimum)[:2]:
        return (
            f"the minimum Home Assistant version {minimum} in {HACS_JSON} is older "
            f"than the oldest tested version {oldest_tested}; raise it and remove "
            "the compatibility code that expires"
        )
    return None


def format_list(markers: list[Marker]) -> str:
    """Return the markers grouped by package and version."""
    lines: list[str] = []
    for package, version in sorted(
        {(marker.package, marker.version) for marker in markers},
        key=lambda item: (item[0], version_key(item[1])),
    ):
        lines.append(f"{package}<{version}")
        lines.extend(
            f"  {marker.path}:{marker.line}: {marker.reason}"
            for marker in markers
            if (marker.package, marker.version) == (package, version)
        )
    return "\n".join(lines)


def report(level: str, problem: Problem) -> None:
    """Print a problem, as an annotation when running in GitHub Actions."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::{level} file={problem.path},line={problem.line}::{problem.message}")
    else:
        print(f"{problem.path}:{problem.line}: {level}: {problem.message}")


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    """Check the markers and return the exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--list", action="store_true", help="list all markers grouped by version"
    )
    parser.add_argument(
        "--minimum",
        metavar="VERSION",
        help="use this minimum Home Assistant version instead of hacs.json",
    )
    parser.add_argument(
        "--oldest-tested",
        metavar="VERSION",
        help="warn if this Home Assistant version is newer than the minimum",
    )
    args = parser.parse_args(argv)

    markers, problems = scan(root)
    minimums = minimum_versions(root)
    if args.minimum:
        minimums[HOMEASSISTANT] = args.minimum
    problems.extend(expired(markers, minimums))

    if args.list:
        print(format_list(markers))

    if args.oldest_tested and (
        warning := minimum_behind_tests(minimums[HOMEASSISTANT], args.oldest_tested)
    ):
        report("warning", Problem(HACS_JSON, 1, warning))

    for problem in problems:
        report("error", problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
