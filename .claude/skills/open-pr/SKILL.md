---
name: open-pr
description: Open a pull request for the ABB-free@home Home Assistant integration, including branching, validating, reviewing the diff, labeling, and writing the description from the repository template. Use when asked to open, create, or submit a PR.
---

# Opening a pull request

Follow the "Pull request scope" and "Issue and pull request labels" sections of
`.github/copilot-instructions.md`; this skill covers the mechanics.

## 1. Branch

- Branch from up-to-date `origin/main` unless the user names another base
  (for example `release/X.Y` for backports). Never open a PR from `main`.
- If the current branch holds unrelated work, create a new branch from the base
  and bring over only the relevant files or commits.
- Name the branch `<prefix>/<short-kebab-topic>`, appending the issue number
  when there is one (for example `feat/cover-requested-position-266`). Use
  exactly one of these prefixes:

  | Prefix      | Use for                                                     |
  | ----------- | ----------------------------------------------------------- |
  | `feat/`     | New entities, platforms, device support, or options         |
  | `fix/`      | Bug fixes                                                   |
  | `refactor/` | Behavior-preserving code changes                            |
  | `docs/`     | Documentation, instructions, and skills                     |
  | `ci/`       | GitHub Actions workflows                                    |
  | `chore/`    | Tests, tooling, dev dependencies, Dev Container, and config |
  | `release/`  | Version bumps and release preparation (see `release` skill) |

- Library pin bumps follow their version impact (see the `bump-library` skill).
- `beta/*` and `alpha/*` are prerelease base branches that CI also runs on; do
  not use them as PR head branches.

## 2. Validate

For any change outside documentation, run with the virtual environment active:

```sh
ruff check .
ruff format --check .
python -m pytest --cov=. --cov-branch --cov-report=term-missing
```

Fix failures and any coverage gaps before continuing; coverage must stay at 100%
and new or changed modules must appear in the report. CI also runs `hassfest`
for changes to `manifest.json`, `strings.json`, `icons.json`, or
`services.yaml`. Record the exact commands and results for the description.

## 3. Review the diff

```sh
git --no-pager diff --stat origin/main...HEAD
git --no-pager diff origin/main...HEAD
```

Remove incidental changes such as unrelated formatting, debug code, or stray
files. Check that no existing entity `unique_id` changed unless the break is
intended. If the diff covers more than one concern, stop and propose a split to
the user.

## 4. Labels

Check that the labels exist with `gh label list`, then choose them according to
the label rules. If the version impact is unclear, ask the user before creating
the PR.

## 5. Description

Fill in every section of `.github/pull_request_template.md`. Keep its headings
and checklist, and tick only the items that are actually true. Under Validation,
list each command with its result. Write the body to a temporary file and pass
it with `--body-file`, because `--body` bypasses the template.

## 6. Create

```sh
git push -u origin <branch>
gh pr create --base <base> --title "<title>" --body-file <file> --label <label> [--label <label>]
gh pr checks <number>
```

Use an imperative, concise title (for example "Add cover requested position
sensor"). Report the PR URL and check status to the user, and delete the
temporary body file.
