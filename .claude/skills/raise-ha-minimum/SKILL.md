---
name: raise-ha-minimum
description: Raise the minimum supported Home Assistant version in hacs.json for the ABB-free@home integration to the oldest release in the CI test matrix, and remove the compatibility code and tests whose `# compat:` markers expire, validating and opening the PR. Use when asked to raise, bump, or update the minimum Home Assistant version, drop support for old Home Assistant versions, or remove expired compatibility code, or when CI warns that the minimum is behind the tested versions.
---

# Raising the minimum Home Assistant version

The integration supports the latest seven Home Assistant minor releases, the
same releases CI tests. The minimum is `homeassistant` in `hacs.json`; HACS does
not offer updates to older installations. Code that exists only for older
versions carries `# compat: homeassistant<X.Y - <reason>` markers, documented in
`.github/instructions/entities.instructions.md`, and
`.github/scripts/check_compat.py` fails once the minimum reaches a marker's
version.

## 1. Pick the target version

```sh
jq -r '.homeassistant // "unset"' hacs.json
python .github/scripts/ha_test_matrix.py --count 7 | jq -r 'map(.homeassistant) | sort_by(split(".") | map(tonumber)) | first'
```

- Use the version the user names, otherwise the minor of the oldest tested
  release, written as `X.Y.0` (for example `2026.6.0` for `2026.6.3`).
- Never raise the minimum above the oldest tested release, because code for
  untested versions would be removed unchecked; never lower it.
- If the target equals the current minimum, report that nothing is due and stop.

## 2. Preview what expires

```sh
python .github/scripts/check_compat.py --minimum <X.Y> --list
```

The errors list every expired marker with its reason. Summarize them for the
user, grouped by version, before editing. Markers that do not expire stay
untouched.

## 3. Raise the minimum

1. Branch from up-to-date `main` as `feat/ha-minimum-<X.Y>`.
2. Set `"homeassistant": "<X.Y>.0"` in `hacs.json`.
3. Update the minimum Home Assistant version in the `README.md` prerequisites,
   and README text describing behavior of versions that are no longer
   supported (for example "On Home Assistant 2026.9 and later").

## 4. Remove the expired compatibility code

Work through the checker's errors until `python .github/scripts/check_compat.py`
passes. For each marker:

- In integration code, keep the path for supported versions and delete the
  marker, the feature detection, and the fallback. For example, a
  `try`/`except ImportError` becomes the plain import, and an
  `if hasattr(...)` whose body is only the fallback is deleted.
- Read the reason and the surrounding code; a marker can guard only part of a
  condition. Where a fallback also serves a case that is not version-related,
  such as the unlinked sub-device used when the parent device is missing, keep
  that case and remove only the version check.
- If a marked block also handles data that older versions left behind, such as
  registry entries that a newer version would create differently, keep it,
  replace the marker with a normal comment explaining why, and point it out to
  the user.
- In tests, delete tests and `parametrize` cases that only exercised the
  fallback, and reduce branches such as `if child_devices_supported:` to their
  supported side. Keep tests of the remaining behavior.
- Remove what becomes unused: imports (such as `inspect`), helpers, type
  aliases, mocks, translation keys named in the reason (from `strings.json` and
  every file in `translations/`), and comments or docstrings describing older
  versions.
- Do not change unmarked code, even if it looks version-related; report it to
  the user as a possibly missing marker instead.

## 5. Validate

```sh
python .github/scripts/check_compat.py
ruff check . && ruff format --check .
python -m pytest --cov=. --cov-branch --cov-report=term-missing
python .github/scripts/test_ha_versions.py
```

The full matrix run must pass with 100% combined coverage. Removing a fallback
can leave a branch that only the oldest versions covered; fix the tests rather
than adding `# pragma: no cover`.

## 6. Open the PR

Use the `open-pr` skill. Title it `Require Home Assistant <X.Y> or newer` and
label it `Semver-Minor` and `enhancement`, regardless of how much code is
removed. In the description, state the old and new minimum, list the removed
compatibility code by marker version, and record the validation. The `release`
skill announces the new minimum in the next release's highlights.
