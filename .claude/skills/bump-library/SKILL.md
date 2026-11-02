---
name: bump-library
description: Bump the local-abbfreeathome library requirement in the ABB-free@home integration's manifest.json, reviewing what changed upstream, adapting the integration to API changes, validating, and planning follow-up entity work. Use when asked to bump, update, or upgrade local-abbfreeathome, or when a feature needs a newer library release.
---

# Bumping local-abbfreeathome

The library is pinned exactly in `custom_components/abbfreeathome_ci/manifest.json`
(`"requirements": ["local-abbfreeathome==A.B.C"]`). Home Assistant installs that
version from PyPI when the integration loads, and CI, the Dev Container, and
`copilot-setup-steps.yml` install it from the same field.

## 1. Pick the target version

```sh
gh release list -R kingsleyadam/local-abbfreeathome --limit 10
jq -r '.requirements[]' custom_components/abbfreeathome_ci/manifest.json
```

- Use the version the user names, otherwise the latest stable release.
- Confirm it is published on <https://pypi.org/p/local-abbfreeathome>; a GitHub
  release without a PyPI upload breaks the integration for every user.
- Do not pin a library prerelease (`a`/`b`) on `main` unless the user asks;
  prerelease pins belong on integration prerelease or `beta/*` branches.

## 2. Review what changed

Read every release between the current pin and the target, including the PRs
behind them, not just titles:

```sh
gh release view <version> -R kingsleyadam/local-abbfreeathome
gh pr view <number> -R kingsleyadam/local-abbfreeathome
```

Sort the changes into:

- **Breaking or behavior changes** (`Semver-Major`, or changed semantics such as
  inverted values): find every use in `custom_components/` and `tests/` with
  `grep`, and plan the required integration changes.
- **New channel classes, attributes, or commands**: candidates for new entities
  with the `add-entity` skill.
- **Fixes**: note which user-visible issues they resolve, including issues in
  this repository they close.

Summarize this for the user before editing.

## 3. Update the pin

1. Branch from up-to-date `main` as `fix/bump-library-<version>`, or
   `feat/...` when the bump delivers user-visible features. For a backport,
   branch from `release/X.Y` instead (see the `release` skill).
2. Update only the `local-abbfreeathome` entry in `manifest.json`.
3. Reinstall and check for dependency conflicts with Home Assistant:

   ```sh
   uv pip install $(jq -r '.requirements[]' custom_components/abbfreeathome_ci/manifest.json)
   uv pip check
   ```

   A conflict with Home Assistant's pinned packages (for example `aiohttp`) would
   prevent the integration from installing; report it rather than working around it.

## 4. Adapt and validate

```sh
python -m pytest --cov=. --cov-branch --cov-report=term-missing
ruff check . && ruff format --check .
```

- If breaking changes require integration changes, make them in the same PR so
  `main` never pins a library it is incompatible with (as in #261), with tests.
- Keep new entities for new library features out of this PR; list them as
  follow-up and implement them with `add-entity` afterwards (as #289 and #291
  did). A bump with no code changes should only touch `manifest.json`.

## 5. Open the PR

Title it `Bump local-abbfreeathome to <version>`, adding the integration version
in parentheses for backports (for example `(1.16.1)`). Label by the impact on
integration users, not the library's label:

- Fixes only: `Semver-Patch` and `bug`.
- New capabilities users get without further changes, such as new function IDs
  mapped to classes the integration already handles: `Semver-Minor` and
  `enhancement`.
- Changes that alter existing entities or require user action:
  `Semver-Major` and `breaking-change`.

Fill in `.github/pull_request_template.md`: summarize the library changes with
links to the library PRs, list required integration changes, record the
validation, and list follow-up entity work under Follow-up.
