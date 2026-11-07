## Summary

<!-- What does this PR do and why? Link the issue or discussion, e.g. "Fixes #123". -->

## Changes

<!-- Changes users will notice: new or changed entities, config options, services. Note anything breaking. -->

-

## Validation

<!-- How was this tested? Unit tests, Home Assistant version, real SysAP and devices, etc. -->

-

## Follow-up

<!-- Work deliberately left for separate PRs, or "None". -->

None

## Checklist

- [ ] Focused on one bug, feature, or refactor, with no unrelated changes
- [ ] Labels applied: `documentation` for docs-only; `chore` for tests, CI,
      tooling, or config only; otherwise exactly one of
      `Semver-Major` (+ `breaking-change`), `Semver-Minor` (+ `enhancement`), or
      `Semver-Patch` (+ `bug` for fixes)
- [ ] Existing entity `unique_id`s are unchanged, or the break is labeled and described
- [ ] Tests added or updated; coverage remains at 100% and changed modules appear in the report
- [ ] `ruff check .` and `ruff format --check .` pass
- [ ] New strings added to `strings.json`, `translations/en.json`, and `translations/de.json` (and `icons.json` where needed)
- [ ] `README.md` updated where behavior, options, or device support changed
