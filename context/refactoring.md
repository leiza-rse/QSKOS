# qskos — Refactoring Plan

A milestone-based plan to pay down the technical debt catalogued in
`context/assessment.md`. Each milestone is self-contained, shippable, and ends
with **tests passing + a commit**, so the plugin never sits in a broken state.
The assessment file is updated as each item is resolved.

---

## Repository layout (post-M0)

The repo root is no longer the plugin package. The plugin lives in a `qskos/`
subdirectory; everything else sits at the repo root:

```
QSKOS/                    <- repo root (git)
├── qskos/                <- the QGIS plugin package (install this folder's
│   │                        contents into QGIS: metadata.txt + __init__.py
│   │                        at the root of the installed folder)
│   ├── __init__.py
│   ├── metadata.txt
│   ├── utils/  tabs/  libs/
├── tests/                <- pytest unit tests (no QGIS runtime required)
├── context/              <- design docs (assessment, architecture, refactor plan)
├── pyproject.toml        <- development env (uv: pytest only)
└── README.md
```

QGIS only requires `metadata.txt` + `__init__.py` at the root of the *installed*
folder, so installing the contents of `qskos/` (e.g. zip that folder) is fully
supported. Tests at the repo root live outside the plugin package, which is what
lets pytest import the pure modules without executing the QGIS entry point.

---

## Architectural decisions (agreed with maintainers)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Canonical annotation storage = JSON string.** Annotation fields become plain text fields holding a JSON-encoded array of concept URIs (`["uri1","uri2"]`). Encode/decode is centralised in **one** module (`utils/fields.py`). | Kills the `QVariant.Map` → OGR round-trip guessing cascade (assessment **A/G**). Deterministic, portable, trivially testable. |
| D2 | **Breaking change, no migration.** New canonical format adopted unconditionally. `parse_field_value` is kept as a *lenient reader* so old values still display/export, but nothing migrates them in place. | Simplest, avoids migration risk on research data. Old fields may display until re-saved. |
| D3 | **Testing = pytest on de-QGIS pure modules.** Pure logic (SQLite, SKOS parsing, hierarchy BFS, LOD graph building) is split into modules with **no QGIS import at import time**. QGIS adapters stay thin. Tests run standalone in CI. | Assessment **I**. |
| D4 | **State = typed `QskosState` object, injected explicitly.** `current_feature_layer` / `current_vocab_layer` / `current_vocab_scheme` etc. become fields on a small state object passed to managers. Fixes the reproduced multi-layer binding bug (assessment **M/D**). | Explicit data flow, testable without a fake plugin. |
| D5 | **Annotation logic = single `AnnotationFieldManager`.** Owns field detection (from config, not field-type sniffing), ValueRelation config building, and encode/decode. `create_annotation_field` and the "reconfigure on load" path both call it. | Removes triple duplication (assessment **B**). |
| D6 | **Milestone commits.** Each milestone = refactor + tests + commit. No big-bang rewrite. | Per maintainer requirement. |
| D7 | **Test runner = `uv`.** `pyproject.toml` declares only dev deps (pytest); runtime deps stay bundled in `qskos/libs/` so the plugin needs no pip install in QGIS. | Matches maintainer preference for `uv`; keeps the plugin self-contained. |

---

## Testing strategy

### Unit / integration (pytest, no QGIS)

Pure layers tested standalone in CI with `uv`:

```
uv sync           # create .venv, install pytest (only dev dep)
uv run pytest     # run the suite (no QGIS required)
```

The pure modules are imported as top-level packages (`import utils.fields`) by
adding `qskos/` to `sys.path` in `tests/conftest.py`. Because tests/ lives at
the repo root (outside the plugin package) and the pure modules are referenced
directly, the plugin root `__init__.py` (which imports PyQt5/QGIS) is never
executed.

Pure layers under test:

- `utils/skos.py` — RDF/CSV parsing, language selection, broader/narrower
  heuristics, scheme backfilling. **First target** (already pure).
- `utils/gpkg.py` — after de-QGISing: config table CRUD, import/export, binding,
  on a real in-memory/temp SQLite file.
- `utils/hierarchy.py` — descendant BFS, tree building, filtered descendants.
- `utils/lod.py` — after de-QGISing the geometry/CRS parts behind a thin adapter:
  graph construction, prefixes, namespace handling, `oa:hasTarget` mapping.
- `utils/fields.py` — JSON encode/decode + lenient `parse_field_value` fallback.

Test layout:

```
tests/
├── conftest.py
├── test_fields.py
├── test_skos.py
├── test_gpkg.py
├── test_hierarchy.py
└── test_lod.py
```

Run: `python -m pytest tests/` (no QGIS required).

### QGIS-bound parts (item I) — 🚧 SCAFFOLDED, not yet verified

The remaining QGIS-touching code (field creation, editor widgets, symbology
renderer, ValueRelation) cannot run in plain pytest. Two complementary options:

1. **pytest-qgis** — runs the same pytest suite *inside* the QGIS Python
   environment (offscreen via `QT_QPA_PLATFORM=offscreen`). Gives real
   `QgsVectorLayer`, real OGR round-trip, real editor widgets. This is the
   closest analogue to a browser test harness for QGIS and is the recommended
   route for the UI/manager logic.
2. **Thin adapters + mocks** — keep manager logic free of direct QGIS calls by
   injecting small adapters, then test the orchestration with fakes. Good for
   the state machine (M3) and `AnnotationFieldManager` (M2) without a QGIS
   runtime.

### End-to-end testing — is there a "Playwright for QGIS"? — 🚧 SCAFFOLDED, not yet verified

There is no browser, so Playwright does not apply directly. But the QGIS
ecosystem has equivalent tooling for driving the real application end-to-end:

- **`pytest-qgis` / `qgis_processing`** run the plugin inside a real QGIS
  session (offscreen), so you can construct the real dock widget, switch tabs,
  bind layers, create fields, generate symbology, and export LOD — i.e. a true
  E2E flow against real QGIS objects, just without a visible window.
- **`qgis_testrunner`** (from `qgis_plugin_tools`) runs a test module inside a
  running QGIS process and reports results back — used by many production
  plugins for integration tests.
- **Qt `QTest`** can simulate real widget events (clicks, key presses, item
  toggles) on the dock widget inside the offscreen QGIS session — this is the
  closest functional equivalent to Playwright's click/type/assert, driving the
  actual signal/slot wiring (`on_tree_item_changed`, `on_load_vocab_clicked`,
  …).
- **Headless CI**: QGIS 3.44 can run with `QT_QPA_PLATFORM=offscreen`,
  `QGIS_NO_OVERRIDE_IMPORT=1`, and `--noplugins`-free startup so the plugin's
  `initGui()` executes.

**Recommended E2E path**: set up a CI job that installs QGIS
(`apt install qgis python3-qgis`) and runs `pytest-qgis` + a `QTest`-driven
scenario test that exercises the full user flow (select GPKG → import vocab →
bind layer → check concept → create field → annotate feature → generate
symbology → export LOD). This gives real coverage of the "latter parts" the
assessment is worried about.

---

## Milestones

> **Status: milestones M0–M8 are implemented** for the pure/unit layers — each
> was landed as its own commit with the pytest suite green, and the assessment
> (`context/assessment.md`) is updated in place. The QGIS-bound / end-to-end
> harness is **scaffolded** (see below) but **not yet verified against a real
> QGIS runtime** — that requires installing QGIS and running
> `scripts/run_qgis_tests.sh` (locally in WSL and/or via the `qgis-tests` CI
> job).

### QGIS-bound / E2E harness — implementation status (item I)

Scaffolded files:

- `tests/test_qgis_plugin.py` — QGIS-bound tests run via **pytest-qgis**
  (offscreen, real `QgsVectorLayer`, real plugin dock widget):
  - plugin boot (`classFactory` + `initGui()` builds the 5-tab dock),
  - `create_annotation_field` round-trips on a real layer (ValueRelation
    editor widget present; idempotent on re-create),
  - `build_value_relation_config` filter lists descendants,
  - multi-layer binding regression guard (assessment item M).
  - Guarded by `pytest.importorskip("pytest_qgis")`, so the plain `uv run
    pytest` (no QGIS) skips it rather than failing.
- `scripts/install_qgis_ubuntu.sh` — installs `qgis` + `python3-qgis` from the
  OSGeo apt repo and `pytest` + `pytest-qgis` into QGIS's Python. Works in WSL
  and in the CI runner (`sudo UBUNTU_CODENAME=noble ...`).
- `scripts/run_qgis_tests.sh` — runs `tests/test_qgis_plugin.py` under QGIS's
  `python3 -m pytest` with `QT_QPA_PLATFORM=offscreen` and the bundled libs on
  `PYTHONPATH`. Same script is used locally (WSL) and in CI.
- `.github/workflows/test.yml` — new **`qgis-tests`** job that installs QGIS
  and runs the harness on every push/PR.

How to run locally (WSL):

```
sudo scripts/install_qgis_ubuntu.sh     # once: installs QGIS + pytest-qgis
scripts/run_qgis_tests.sh               # runs the QGIS-bound suite (offscreen)
```

> **Still to do** — verify the harness against a real QGIS runtime (boot the
> WSL/CI QGIS), fix any API mismatches surfaced, and optionally extend the
> scenario with a Qt `QTest`-driven dock-widget interaction test (click a
> concept in the tree → field created via `on_tree_item_changed`).

### M0 — ✅ DONE — Repo restructure into `qskos/` subdir (testability prerequisite)

- Move the plugin package (`__init__.py`, `metadata.txt`, `utils/`, `tabs/`,
  `libs/`, sample data) into a `qskos/` subdirectory.
- Move `tests/`, `context/`, `pyproject.toml`, `.gitignore` to the repo root.
- Add `__init__.py` to `utils/` and `tabs/` (proper subpackages).
- `tests/conftest.py` adds `qskos/` and `qskos/libs/` to `sys.path`.
- Set up `uv` (pyproject with pytest as the only dev dep).
- **Done**: `uv run pytest` runs the first `test_fields.py` suite green.
- **QGIS impact**: install the contents of `qskos/` (zip that folder), not the
  repo root. QGIS only needs `metadata.txt` + `__init__.py` at the installed
  folder's root.

### M1 — ✅ DONE — Canonical JSON annotation storage (A, G)

- `utils/fields.py`: add `encode_annotation_values(list[str]) -> str` (JSON) and
  keep `parse_field_value` as a lenient reader (accept JSON, list, pipe, single).
- `AnnotationFieldManager` field creation uses a **text** field (not
  `QVariant.Map`) with JSON default `"[]"`.
- Tests: `test_fields.py`.

### M2 — ✅ DONE — Extract `AnnotationFieldManager` (B)

- New `utils/annotation.py` (pure-ish) + a QGIS adapter owning:
  1. detecting annotation fields **from the config table** + bound vocab (not
     field-type sniffing),
  2. building the ValueRelation config given `(feature_layer, vocab_layer,
     concept_uri)`,
  3. encode/decode via `utils/fields.py`.
- `create_annotation_field`, `_reconfigure_annotation_field`,
  `reinitialize_all_annotation_fields_for_layer` all delegate to it.
- Deduplicate the `_concept_belongs_to_vocab` / `_get_concept_label_from_*`
  lookups using a single URI→label dict built once.
- Tests: `test_annotation.py` (with adapter fakes / pytest-qgis).

### M3 — ✅ DONE — `QskosState` + explicit injection (D, M)

- New `state.py` defining a `QskosState` dataclass (`active_gpkg_path`,
  `current_feature_layer`, `current_vocab_layer`, `current_vocab_scheme`,
  `selected_language`, hierarchy cache) with getters/setters + change signals.
- Managers receive the state object explicitly instead of fishing off
  `self.plugin`.
- Fixes the reproduced multi-layer binding bug.
- Tests: `test_state.py` (state transitions, no QGIS).

### M4 — ✅ DONE — De-QGIS pure utils + full pytest suite (I)

- `utils/gpkg.py`: keep pure SQLite funcs (config CRUD, import) QGIS-free; move
  `ensure_vocab_layer_loaded` / path-helper-that-needs-QGIS into a thin adapter.
- `utils/lod.py`: extract geometry/CRS handling behind an injectable geometry
  adapter so the graph builder has no QGIS import.
- `utils/hierarchy.py`: already Qt-free except `build_concept_tree_from_layer`
  (QTreeWidget) — split the pure index/BFS from the widget tree builder.
- Full `tests/` suite runnable standalone.
- Add CI (GitHub Actions) running `pytest`.

### M5 — ✅ DONE — Hierarchy cache + single-pass feature reads (E, C)

- Key hierarchy cache by `(gpkg path, table name, content hash/mtime)` instead
  of volatile `layer.id()`.
- Invalidate on vocab import only.
- Symbology/LOD: single `getFeatures()` pass building a `concept_uri →
  features` inverted index instead of one pass per field.

### M6 — ✅ DONE — Deterministic symbology + polyhierarchy (F, K)

- Stable colour derived from concept URI hash (drop `random`).
- Ancestor walk handles multiple `broader` parents (polyhierarchy).
- Prefer `array_intersect`/`array_contains_any` over `OR`-chained
  `array_contains`; deduplicate redundant descendant re-listing.

### M7 — ✅ DONE — Error handling + logging (J, K)

- Replace `print()` with `QgsMessageLog`.
- Replace bare `except: pass/continue` with specific catches + logging in
  symbology, LOD export, and layer tree load.
- Doc/pin the `libs/` rdflib purge hack.

### M8 — ✅ DONE — Tighten RDF heuristics (L)

- Per-concept `narrower` fallback (not global).
- Prefer subjects typed `skos:Concept`; keep prefLabel fallback as last resort.
- Fix stale LOD header comment; persist object namespace in config.

---

## Ordering rationale

Milestones are ordered to reduce risk first (storage model → field logic →
state) before optimisation (cache/reads → symbology) and cleanup (logging →
heuristics). Each is independently commit-worthy; the assessment is updated
incrementally rather than all at the end.
