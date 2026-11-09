# WP-001: Tooling baseline

Status: draft

Tier: cheap   ·   Depends on: –   ·   Size: S

## Goal
Lint runs locally and in CI, `make test` runs before every push, and `make package` builds an installable plugin zip.

## Read first
`Makefile`, `pyproject.toml`, `.github/workflows/test.yml`, `.gitignore`, `qskos/metadata.txt`.

## Tasks
1. Add `ruff` to the `dev` dependency group; configure it in `pyproject.toml` (exclude `qskos/libs`, `docs`; rules `E,F,W,I,B`, line
   length 120). Fix what it reports in `qskos/`, `tests/`, `tools/` without behaviour changes (separate commit).
2. `make lint`; `make test` runs lint + `uv run pytest`. CI job `pytest` runs `make test`.
3. `scripts/hooks/pre-push` running `make test` (and `make test-qgis` when `.venv-qgis` exists); `make hooks` installs it via
   `git config core.hooksPath scripts/hooks`.
4. `make package`: zip `qskos/` (without `__pycache__`, tests) to `dist/qskos-<version from metadata.txt>.zip` with `qskos/` as top folder.
5. `.gitignore`: `dist/`, QGIS leftovers in the repo root (`*.db` style databases, `_attachments.zip`).

## Acceptance criteria
- `make test` fails on a lint error and passes on the cleaned tree; CI runs it.
- `make package` creates a zip that installs via QGIS "Install from ZIP" (human check) and contains no tests or caches (`unzip -l`).

## Tests required
None beyond existing suites; the lint run is the check.

## Out of scope
Refactors beyond what ruff flags; `pyright`/type checking.

## Human steps
Install the zip once in QGIS desktop.
