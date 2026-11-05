"""Run the test suite against the supported Home Assistant releases, like CI.

Mirrors `.github/workflows/test-ha-versions.yaml`: runs pytest with coverage in
an isolated uv environment for each version from `ha_test_matrix.py`, then
combines the coverage. The 100% gate applies only when the full matrix ran
without extra pytest arguments.

Examples:
    python .github/scripts/test_ha_versions.py
    python .github/scripts/test_ha_versions.py --html
    python .github/scripts/test_ha_versions.py --ha 2026.6
    python .github/scripts/test_ha_versions.py --ha 2025.12.1 --with 'pycares<5'
    python .github/scripts/test_ha_versions.py --ha 2026.11 -- tests/test_light.py -x
    python .github/scripts/test_ha_versions.py -- -rA

"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from ha_test_matrix import build_matrix

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "custom_components/abbfreeathome_ci/manifest.json"


def uv_run(python: str, packages: list[str], args: list[str], env: dict) -> int:
    """Run a command in a throwaway uv environment and return its exit code."""
    minor = ".".join(python.split(".")[:2])
    request = f">={python},=={minor}.*"
    command = ["uv", "run", "--isolated", "--no-project", "--python", request]
    for package in packages:
        command += ["--with", package]
    return subprocess.run(
        command + args, cwd=REPO_ROOT, env=env, check=False
    ).returncode


def main() -> None:
    """Run the matrix and report the results."""
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Arguments after -- are passed to pytest.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=7,
        help="number of latest minor releases to include (default: 7)",
    )
    parser.add_argument(
        "--ha",
        action="append",
        default=[],
        metavar="VERSION",
        help=(
            "run this Home Assistant version instead of the supported ones, "
            "e.g. 2026.1 (newest patch) or 2026.1.2 (repeatable)"
        ),
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="also write an HTML coverage report to htmlcov/",
    )
    parser.add_argument(
        "--with",
        action="append",
        default=[],
        dest="packages",
        metavar="PACKAGE",
        help="install an extra package or constraint, e.g. 'pycares<5' (repeatable)",
    )
    args, pytest_args = parser.parse_known_args()
    if pytest_args[:1] == ["--"]:
        pytest_args = pytest_args[1:]

    matrix = build_matrix(args.count, args.ha)

    requirements = json.loads(MANIFEST.read_text(encoding="utf-8"))["requirements"]
    env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    # Home Assistant pins its own uv, which may be too old to know the
    # required Python, so keep the active virtual environment off the PATH.
    if venv := os.environ.get("VIRTUAL_ENV"):
        venv_bin = str(Path(venv, "bin"))
        env["PATH"] = os.pathsep.join(
            path for path in env.get("PATH", "").split(os.pathsep) if path != venv_bin
        )
    results: dict[str, int] = {}

    with tempfile.TemporaryDirectory(prefix="ha-coverage-") as coverage_dir:
        for entry in matrix:
            version = entry["homeassistant"]
            print(f"\n=== Home Assistant {version} ({entry['plugin']})", flush=True)
            results[version] = uv_run(
                entry["python"],
                [entry["plugin"], "pytest-cov", *requirements, *args.packages],
                [
                    "python",
                    "-m",
                    "pytest",
                    "-p",
                    "no:cacheprovider",
                    "--cov",
                    "--cov-branch",
                    "--cov-report=",
                    *pytest_args,
                ],
                {**env, "COVERAGE_FILE": f"{coverage_dir}/.coverage.{version}"},
            )

        print("\n=== Combined coverage", flush=True)
        data_file = f"{coverage_dir}/.coverage"
        coverage_env = {**env, "COVERAGE_FILE": data_file}
        python = matrix[0]["python"]
        coverage_failed = uv_run(
            python, ["coverage"], ["coverage", "combine", coverage_dir], coverage_env
        ) or uv_run(
            python,
            ["coverage"],
            ["coverage", "report", "--show-missing"]
            + (["--fail-under=100"] if not args.ha and not pytest_args else []),
            coverage_env,
        )
        if args.html:
            uv_run(python, ["coverage"], ["coverage", "html", "-q"], coverage_env)
            print(f"HTML report: {REPO_ROOT / 'htmlcov/index.html'}")

    print("\n=== Results")
    for version, code in results.items():
        print(f"{version}: {'passed' if code == 0 else 'FAILED'}")
    print(f"coverage: {'FAILED' if coverage_failed else 'passed'}")
    sys.exit(1 if coverage_failed or any(results.values()) else 0)


if __name__ == "__main__":
    main()
