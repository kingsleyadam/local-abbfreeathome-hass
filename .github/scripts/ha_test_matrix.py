"""Build the CI test matrix for the supported Home Assistant releases.

Selects the newest patch release of each of the latest Home Assistant minor
releases on PyPI, together with the pytest plugin and the Python version it
needs. From 2026.11 on, Home Assistant publishes `pytest-homeassistant` with the
same version numbers, betas included; older releases use the matching
`pytest-homeassistant-custom-component` release, which pins `homeassistant`.

With `--ha`, selects the given versions instead; with `--beta`, the newest beta
of an upcoming release, or nothing while there is none.

Prints the matrix as JSON and, in GitHub Actions, writes it to the `matrix`
step output.
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import sys
from typing import Any
import urllib.request

PYPI_URL = "https://pypi.org/pypi/{package}/json"
HA_PACKAGE = "homeassistant"
HA_PLUGIN = "pytest-homeassistant"
CUSTOM_COMPONENT_PLUGIN = "pytest-homeassistant-custom-component"

VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)(?:b(\d+))?")
HA_PIN = re.compile(r"^homeassistant==(\d+\.\d+\.\d+)$")
MIN_PYTHON = re.compile(r">=\s*(\d+\.\d+(?:\.\d+)?)")


@functools.cache
def fetch(package: str, version: str | None = None) -> dict[str, Any]:
    """Return the PyPI JSON metadata of a package or one of its releases."""
    name = f"{package}/{version}" if version else package
    request = urllib.request.Request(
        PYPI_URL.format(package=name), headers={"User-Agent": "ha-test-matrix"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def version_key(version: str) -> tuple[int, ...]:
    """Return a sortable key for a stable or beta version string.

    A beta sorts before the release it leads up to.
    """
    *release, beta = VERSION.fullmatch(version).groups()
    return (*map(int, release), sys.maxsize if beta is None else int(beta))


def _releases(
    metadata: dict[str, Any], *, beta: bool
) -> dict[str, list[dict[str, Any]]]:
    """Return the non-yanked stable releases or betas with their files."""
    return {
        version: files
        for version, files in metadata["releases"].items()
        if (match := VERSION.fullmatch(version))
        and (match[4] is not None) is beta
        and files
        and not all(file["yanked"] for file in files)
    }


def stable_releases(metadata: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Return the stable, non-yanked releases with their files."""
    return _releases(metadata, beta=False)


def beta_releases(metadata: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Return the non-yanked betas with their files."""
    return _releases(metadata, beta=True)


def custom_component_plugins(oldest: tuple[int, ...]) -> dict[str, str]:
    """Map Home Assistant versions to their custom component plugin version.

    Walks the plugin releases from newest to oldest and stops once they pin a
    Home Assistant version older than `oldest`.
    """
    plugins: dict[str, str] = {}
    for version in sorted(
        stable_releases(fetch(CUSTOM_COMPONENT_PLUGIN)), key=version_key, reverse=True
    ):
        requires = fetch(CUSTOM_COMPONENT_PLUGIN, version)["info"]["requires_dist"]
        pins = [match[1] for req in requires or [] if (match := HA_PIN.match(req))]
        if not pins:
            continue
        if version_key(pins[0]) < oldest:
            break
        plugins.setdefault(pins[0], version)
    return plugins


def build_matrix(count: int, versions: list[str] | None = None) -> list[dict[str, str]]:
    """Return the matrix entries for the latest `count` minor releases.

    With `versions`, return one entry for each given version instead, which may
    be a full release such as 2026.1.2, a beta such as 2026.2.0b1, or a prefix
    such as 2026.1, matching its newest patch, or its newest beta until the
    release is out. Any release with a pytest plugin works, supported or not.
    """
    metadata = fetch(HA_PACKAGE)
    releases = stable_releases(metadata)

    groups: list[tuple[str, list[str]]] = []
    if versions:
        betas = beta_releases(metadata)
        for spec in versions:
            matches = [v for v in releases if f"{v}.".startswith(f"{spec}.")]
            matches = matches or [v for v in betas if f"{v}.".startswith(f"{spec}.")]
            if not matches:
                sys.exit(f"No Home Assistant release matches {spec}")
            groups.append((spec, matches))
        releases |= betas
    else:
        minors: dict[tuple[int, ...], list[str]] = {}
        for version in releases:
            minors.setdefault(version_key(version)[:2], []).append(version)
        groups = [
            (".".join(map(str, minor)), minors[minor])
            for minor in sorted(minors, reverse=True)[:count]
        ]

    plugin_metadata = fetch(HA_PLUGIN)
    ha_plugins = {*stable_releases(plugin_metadata), *beta_releases(plugin_metadata)}
    custom_plugins = custom_component_plugins(
        min(version_key(version) for _, group in groups for version in group)
    )

    matrix = []
    for name, group in groups:
        for version in sorted(group, key=version_key, reverse=True):
            if version in ha_plugins:
                plugin = f"{HA_PLUGIN}=={version}"
            elif version in custom_plugins:
                plugin = f"{CUSTOM_COMPONENT_PLUGIN}=={custom_plugins[version]}"
            else:
                continue
            requires_python = releases[version][0]["requires_python"] or ""
            if not (python := MIN_PYTHON.search(requires_python)):
                sys.exit(f"Cannot read the Python version of {HA_PACKAGE} {version}")
            matrix.append(
                {"homeassistant": version, "python": python[1], "plugin": plugin}
            )
            break
        else:
            sys.exit(f"No pytest plugin found for Home Assistant {name}")
    return matrix


def beta_matrix() -> list[dict[str, str]]:
    """Return the matrix entry for the newest beta of an upcoming release.

    The matrix is empty while no beta is newer than the latest release, or
    while the pytest plugin of the newest beta is not published yet.
    """
    metadata = fetch(HA_PACKAGE)
    latest = max(map(version_key, stable_releases(metadata)))
    upcoming = [v for v in beta_releases(metadata) if version_key(v) > latest]
    if not upcoming:
        return []
    newest = max(upcoming, key=version_key)
    if newest not in beta_releases(fetch(HA_PLUGIN)):
        print(f"No pytest plugin for Home Assistant {newest} yet", file=sys.stderr)
        return []
    return build_matrix(0, [newest])


def main(argv: list[str] | None = None) -> None:
    """Print the matrix and write it to the GitHub Actions step output."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--count",
        type=int,
        default=7,
        help="number of latest minor releases to include (default: 7)",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--ha",
        action="append",
        metavar="VERSION",
        help=(
            "select this Home Assistant version instead, e.g. 2026.1 (newest "
            "patch), 2026.1.2, or 2026.2.0b1 (repeatable)"
        ),
    )
    selection.add_argument(
        "--beta",
        action="store_true",
        help="select the newest beta of an upcoming release instead, if any",
    )
    args = parser.parse_args(argv)
    matrix = beta_matrix() if args.beta else build_matrix(args.count, args.ha)

    print(json.dumps(matrix, indent=2))
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as file:
            file.write(f"matrix={json.dumps(matrix)}\n")


if __name__ == "__main__":
    main()
