# WP-007: QGIS 4 readiness and cleanups

Status: draft

Tier: cheap   ·   Depends on: WP-001   ·   Size: S

## Goal
The plugin imports Qt through `qgis.PyQt`, runs without deprecation warnings on QGIS 3.44, narrows broad exception handlers, and offers
the import languages the source actually contains.

## Read first
`context/open-questions.md` Q6, Q15; `grep -rln "from PyQt5" qskos` (7 files); warnings printed by `make test-qgis`.

## Tasks
1. Replace `PyQt5` imports with `qgis.PyQt` in `qskos/` and tests.
2. Fix deprecations: `QgsField(name, QVariant…)` → the `QMetaType` constructor (keep the exact native JSON type, ADR-0001),
   `QgsMapLayerComboBox.setFilters` → `Qgis.LayerFilter`.
3. The 11 `except Exception` blocks: catch the specific errors (`sqlite3.Error`, `RuntimeError`, rdflib parse errors…) or log with
   context and re-raise; none may swallow silently.
4. Q6: after parsing a source, fill the language combo with the language tags found (prefLabel), default as today.
5. Set `qgisMaximumVersion=4.99` in `metadata.txt` only if Q15 is decided "yes".

## Acceptance criteria
- `make test-qgis` prints no `DeprecationWarning` from `qskos/`.
- `grep -rn "PyQt5" qskos tests` returns nothing.
- A test imports a vocabulary with `fr` labels and gets `fr` offered.

## Tests required
Language detection test (pure, in `tests/test_skos.py`); existing suites.

## Out of scope
A QGIS 4 CI job (follow-up once QGIS 4 packages exist for Ubuntu).

## Human steps
Decide Q6 and Q15.
