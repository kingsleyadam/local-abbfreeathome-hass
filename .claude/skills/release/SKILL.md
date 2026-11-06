---
name: release
description: Prepare and publish an ABB-free@home Home Assistant integration release to GitHub and HACS, including choosing the version, checking the library pin, the release PR, release highlights, tagging, prereleases, and backport releases from release/X.Y branches. Use when asked to cut, prepare, tag, or publish a release or bump the integration version.
---

# Releasing the ABB-free@home integration

Pushing a tag is effectively irreversible: it creates a GitHub release that HACS
offers to users immediately. Never push a tag without explicit confirmation from
the user of the exact tag and commit.

## How publishing works

- `.github/workflows/release.yml` runs on every push but only creates a GitHub
  release, with generated notes, on tag pushes. It does not run tests; CI on the
  tagged commit must already be green.
- HACS installs from GitHub releases. Users only see prereleases if they enable
  beta versions for the integration in HACS.
- Tags are bare versions with no `v` prefix: `1.16.1`, `1.17.0b1`.
- Tags containing `a` or `b` are created as GitHub prereleases.
- If `.github/release-notes/<exact-tag>.md` exists at the tagged commit, it is
  prepended to the generated notes (see `.github/release-notes/README.md`).
- Generated notes are grouped by PR labels using `.github/release.yml`.
- The version lives only in `custom_components/abbfreeathome_ci/manifest.json`
  (`"version": "X.Y.Z"`). The library dependency is pinned in the same file's
  `requirements` (`local-abbfreeathome==A.B.C`); Home Assistant installs it from
  PyPI when the integration loads.

## 1. Choose the version

1. Find the latest release and the PRs merged since it:

   ```sh
   git fetch --tags origin
   gh release list --limit 5
   gh pr list --state merged --base main --search "merged:>$(git log -1 --format=%cI <last-tag>)" \
     --json number,title,labels --limit 100
   ```

   The latest release may come from a `release/X.Y` branch (for example `1.16.1`)
   while `main` still has an older version; compare against the last tag reachable
   from `main` (`git describe --tags --abbrev=0 origin/main`).

2. Pick the bump from the highest version-impact label among those PRs:
   `Semver-Major` -> major, `Semver-Minor` -> minor, otherwise patch.
   Flag any merged PR missing a version-impact label (documentation-only and
   `chore` PRs are exempt) and confirm the version with the user before
   continuing.

## 2. Check the library pin

Read the `local-abbfreeathome` pin in `manifest.json` and confirm:

- The pinned version is published on <https://pypi.org/p/local-abbfreeathome>;
  an unpublished pin makes the integration fail to load for every user.
- A stable release does not pin a library prerelease.
- Whether a newer library release exists that users need. If so, ask the user
  whether to bump it in a separate PR first; do not fold it into the release PR.

## 3. Open the release PR

1. Branch from up-to-date `main` as `release/X.Y.Z`.
2. Update `version` in `manifest.json`.
3. Check `.github/release-notes/` for a file matching the exact tag. Feature PRs
   often add highlights ahead of the release (for example `1.17.0.md`); review it
   against what actually merged rather than writing a new one.
4. Review the changes since the last tag (PR descriptions and diffs, not just
   titles) for anything worth calling out to users: new device support or
   entities, new config options or services, behavior changes, breaking changes
   such as changed entity IDs or removed options, and required Home Assistant or
   library versions. Present a short list of candidates with the reason each
   matters, and ask the user which, if any, to include or add. Write or update
   `.github/release-notes/X.Y.Z.md` following the style of existing files there:
   a `## New: <feature>` heading per item, a short user-facing explanation that
   names the relevant integration options as they appear in the UI, and a link
   to the wiki or README for setup details. If nothing stands out or the user
   declines, rely on the generated notes.

   If the minimum Home Assistant version changed since the last tag (check with
   `git diff <last-tag> HEAD -- hacs.json`, usually from a `raise-ha-minimum`
   PR), highlights are required, even if nothing else stands out. Put it first
   in the file, before any other section, as
   `## Requires Home Assistant X.Y or newer`. Say that HACS does not offer this
   release to older installations, so users must update Home Assistant first,
   and link to the README prerequisites.
5. Run the validation from `.github/copilot-instructions.md` (`ruff check .`,
   `ruff format --check .`, and `pytest` with coverage) and record the results.
6. Open a PR to `main` titled `Bump version to X.Y.Z`, or
   `Prepare X.Y.Z release` when it includes highlights. Label it with the
   matching `Semver-Major`/`Semver-Minor`/`Semver-Patch`, plus `documentation`
   when it includes highlights, and fill in `.github/pull_request_template.md`.
7. Wait for CI (tests, Ruff, and hassfest) to pass and for the user to merge it.

## 4. Tag and publish

1. After the PR is merged, find the merge commit on `main` and confirm CI passed
   on it:

   ```sh
   git fetch origin main
   git log -1 --format='%h %s' origin/main   # confirm it is the release PR
   gh run list --commit "$(git rev-parse origin/main)"
   ```

2. Show the user the tag name and commit, and get explicit confirmation. Then:

   ```sh
   git tag X.Y.Z origin/main
   git push origin X.Y.Z
   ```

3. Watch the release run and verify the result:

   ```sh
   gh run list --workflow release.yml --branch X.Y.Z   # runs on every push; filter by tag
   gh run watch <run-id>
   gh release view X.Y.Z
   ```

   Check that the highlights, if any, appear above the generated notes and that
   the release is marked as a prerelease only for `a`/`b` tags.

## Prereleases

Use tags such as `X.Y.Zb1`, with the same value in `manifest.json`, and follow the
same steps. Release notes match the exact tag, so a prerelease needs its own file
(for example `1.16.0b1.md`); when promoting to stable, add `X.Y.Z.md` too, reusing
the prerelease highlights where they still apply. Ask the user to confirm the
prerelease works on a real installation before promoting it.

## Backport releases

Use these to ship a fix for an older minor line without the unreleased features
on `main`, for example `1.16.1` while `main` holds 1.17 work.

1. Create `release/X.Y` from the last tag of that line if it does not exist
   (`git switch -c release/X.Y X.Y.Z && git push -u origin release/X.Y`).
2. Branch from `release/X.Y`, cherry-pick or apply the fix, and bump `version` in
   `manifest.json` in the same PR. Open the PR against `release/X.Y` with the
   version in the title (for example `Bump local-abbfreeathome to 3.10.1 (1.16.1)`)
   and the usual labels.
3. Wait for CI (tests, Ruff, and hassfest) to pass on the PR and for the user to
   merge it. Then confirm CI passed on the head of `release/X.Y`, get explicit
   confirmation, and tag that commit and push the tag as above.
4. GitHub marks the newest-created stable release as "Latest". If a newer
   version line already exists, restore it afterwards:

   ```sh
   gh release edit <newest-tag> --latest
   ```

5. Make sure the fix also lands on `main` if it applies there.
