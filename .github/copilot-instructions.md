# Repository instructions

## Build, test, and lint

This is the ABB-free@home Home Assistant custom integration, distributed through
HACS. The integration lives in `custom_components/abbfreeathome_ci` with domain
`abbfreeathome_ci`. The Dev Container uses Python 3.14, and CI tests each Home
Assistant version on the Python it requires; the Ruff CI job uses Python 3.12.
Use `uv` to manage the virtual environment; it is the Dev Container default. Run
commands from the repository root with the virtual environment active.

```sh
uv venv
source .venv/bin/activate
uv pip install -r dev-requirements.txt
uv pip install $(jq -r '.requirements[]' custom_components/abbfreeathome_ci/manifest.json)
pre-commit install

python -m pytest
python -m pytest tests/test_light.py
python -m pytest tests/test_light.py::test_simple_light_is_on
python -m pytest --cov=. --cov-branch --cov-report=term-missing
ruff check .
ruff format --check .
```

The Dev Container's `postCreateCommand` already runs these install steps and
`pre-commit install`. `dev-requirements.txt` pins Home Assistant's
`pytest-homeassistant` plugin, which in turn pins the latest Home Assistant
release for local tests. The library version comes from `requirements` in
`manifest.json`; reinstall from it after changing the pin.

To run Home Assistant with the integration, start the `Home Assistant`
configuration under VS Code's Run and Debug. It runs Home Assistant from the
virtual environment under the debugger, with the git-ignored `config/` directory
as its configuration, and loads the integration from `custom_components` through
`PYTHONPATH`, so breakpoints in the integration, Home Assistant, and the library
work. The frontend listens on port 8123.

Pre-commit runs Ruff with `--fix` and the Ruff formatter. Ruff configuration lives
in `pyproject.toml`, including docstring checks, import sorting with
`homeassistant` as first party, and bans on `async_timeout` and `pytz` in favor of
`asyncio.timeout` and `zoneinfo`. CI also runs `hassfest`, which validates
`manifest.json`, `strings.json`, `icons.json`, and `services.yaml`.

CI's `Test Results` gate requires 100% line and branch coverage; every change
must keep it there by adding tests for new or changed code. Only when a path is
genuinely untestable may it be excluded with `# pragma: no cover`, ideally with a
short reason. `custom_components` has no `__init__.py`, so coverage only reports
modules that tests import; a module without tests is invisible to the gate. Do
not treat a passing gate as proof that a new or changed module is covered; check
that it appears in the report.

CI runs the suite against the newest patch of each of the latest seven Home
Assistant minor releases (`.github/workflows/test-ha-versions.yaml`), weekly and
on pushes and PRs. `.github/scripts/ha_test_matrix.py` picks the versions from
PyPI, with the matching pytest plugin and Python version; run it to see the
current matrix. The coverage of all versions is combined, and the combined report
must reach 100%, so code that branches on the Home Assistant version needs
tests that cover each branch on some version in the matrix.

While a Home Assistant beta leads up to the next release,
`.github/workflows/test-ha-beta.yaml` runs the suite against the newest beta
(`ha_test_matrix.py --beta`) hourly, once per beta and commit of `main`. It has no
coverage gate and is not a required check. Failing tests open an issue labeled
`bug`, or comment on the open one, and the next passing run closes it; after a
failure before the tests, such as a PyPI error, the next hourly run retries. A
fix that keeps the old code path for older supported releases marks it with a
`# compat:` marker, described below. To test a given version, run the workflow
manually with that version.

To reproduce this locally, `python .github/scripts/test_ha_versions.py` (aliased
to `run-tests` in the Dev Container, and available under VS Code's Run and Debug
through `.vscode/launch.json`) runs the whole matrix in isolated uv
environments and applies the same coverage gate.
`--ha 2026.6` runs that version instead, any release with a pytest plugin even
outside the supported range, or a beta such as `--ha 2026.12.0b1`; a prefix such
as `--ha 2026.12` picks the newest beta until that release is out.
`--with PACKAGE` adds an extra package or constraint, such as `'pycares<5'` for
2025.12. `--html` also writes `htmlcov/`, and arguments after `--` go to pytest
(for example `-- tests/test_light.py -x`); the gate applies only to a full run
without `--ha` or pytest arguments.

The minimum supported Home Assistant version is `homeassistant` in `hacs.json`.
Compatibility code for older versions carries `# compat:` markers, described in
`entities.instructions.md`; `python .github/scripts/check_compat.py` fails on
markers the minimum has passed and runs in pre-commit and CI. The Home
Assistant test workflow, including its weekly run, warns when the oldest tested
release is newer than the minimum, which is the cue to raise it and remove the
code the checker then reports with the `raise-ha-minimum` skill.

## Architecture

The integration is a thin Home Assistant layer over the
[`local-abbfreeathome`](https://github.com/kingsleyadam/local-abbfreeathome)
library (imported as `abbfreeathome`), which talks to the ABB/Busch-Jaeger
free@home SysAP **Local API**. Protocol, device, and channel logic belongs in the
library; this repository maps library channels to Home Assistant entities. When a
feature needs new library behavior, make that change in the library first, release
it, and then bump the `manifest.json` requirement here.

- `__init__.py`: `async_setup_entry()` loads `FreeAtHomeSettings`, builds a
  `FreeAtHome` object with the interfaces selected by the entry options, calls
  `load()`, registers the SysAP and each device with visible channels in the
  device registry, stores the object in `hass.data[DOMAIN][entry.entry_id]`, and
  forwards `PLATFORMS`. It then starts `ws_listen()` as an entry background task;
  WebSocket updates reach entities through library channel callbacks, so entities
  do not poll. A devices-changed callback adds or removes devices at runtime and
  fans changes out through dispatcher signals. It also registers the
  `virtual_device` service and handles YAML import and config-entry migration.
- `entity.py`: `async_setup_platform_entities()` is the shared platform setup.
  It builds entities for current channels and for channels added at runtime,
  deduplicates by `unique_id`, and forgets entities of removed devices.
  `FreeAtHomeEntity` is the base class; it marks entities unavailable while the
  backing device is unresponsive.
- Platform modules (`binary_sensor.py`, `sensor.py`, `switch.py`, and so on): one
  per Home Assistant platform, mostly table-driven. `sensor.py` also exposes a
  per-device parameters sensor.
- `config_flow.py`: user, SSL, zeroconf discovery, YAML import, and reconfigure
  steps; the SysAP serial is the config entry's unique ID.
- `diagnostics.py`: config-entry diagnostics with SysAP configuration, redacting
  location and identifying fields.
- `helpers.py`: compatibility helpers for supporting a range of Home Assistant
  versions (for example `via_device` versus `via_device_id`).

## Path-specific instructions

Detailed conventions live in `.github/instructions/*.instructions.md`, scoped by
their `applyTo` globs. Read the matching file before changing code in its scope
if it is not already loaded.

- `entities.instructions.md` (`custom_components/**/*.py`, `tests/**/*.py`):
  entity, platform, device, config-entry, and library-usage conventions.
- `translations.instructions.md` (`custom_components/**/*.json`,
  `custom_components/**/services.yaml`): `strings.json`, translations, and icons.
- `tests.instructions.md` (`tests/**`): test structure, fixtures, and mocking patterns.

## Pull request scope

Keep PRs small and easy to review: each PR should address one focused bug,
feature, or refactor, with only the tests and documentation needed for that change.
Do not bundle unrelated fixes, cleanup, dependency upgrades, renames, or formatting
changes. Format touched code without reformatting unrelated files.

For larger work, propose a split into independently reviewable, working PRs before
implementing the full change. Separate preparatory refactors from behavior changes
when each can stand on its own; keep tightly coupled changes together rather than
leaving broken intermediate states. If the scope grows beyond the original task,
pause and agree on the split instead of silently expanding the PR.

Before opening a PR, inspect the complete diff and remove incidental changes.
Keep the description concise: state the purpose, behavioral changes, and validation,
and identify any follow-up work deliberately left for separate PRs.

## Issue and pull request labels

Every new issue and PR must have at least one relevant label. Inspect existing
repository labels and apply them when creating the issue or PR; do not leave
labeling as a follow-up task or invent new labels without agreement.

For documentation-only PRs, `documentation` is the only required label. For
chore PRs, which change neither code nor documentation (for example CI, tooling,
the Dev Container, or repository configuration), `chore` is the only required
label. Neither needs a version-impact label.

For all other PRs, also apply exactly one version-impact label:

- `Semver-Major`: breaking changes; also add `breaking-change`.
- `Semver-Minor`: backward-compatible features; also add `enhancement`.
- `Semver-Patch`: bug fixes or backward-compatible refactors; add `bug` for fixes.

For this integration, changing an existing entity's `unique_id`, removing an
entity or platform, or removing a config option is breaking. New entities,
platforms, or device support are features. Bumping the library pin follows the
impact of what it brings to users.

Use additional labels such as `documentation` or `question` when applicable.
If the version impact is unclear, ask before creating the PR rather than guessing.
PR labels categorize generated release notes via `.github/release.yml` and inform
the required version bump. Keep labels consistent with the actual change, updating
them if the PR scope changes.

## Releases

The integration version is `version` in
`custom_components/abbfreeathome_ci/manifest.json`. Pushing a tag (bare version,
no `v` prefix) creates a GitHub release with generated notes, which HACS picks up;
tags containing `a` or `b` become prereleases. Optional release highlights belong
in `.github/release-notes/<exact-tag>.md` and must be merged before pushing the
tag, as documented in `.github/release-notes/README.md`.
