# WP-002: `GpkgStore` class for all GeoPackage access

Status: draft

Tier: strong+review   ·   Depends on: WP-001   ·   Size: M

## Goal
All GeoPackage reads/writes go through one `GpkgStore(path)` object with a small query surface; tabs no longer open SQLite connections
indirectly 22 times per action, and the "for each bound scheme → table → vocab layer → hierarchy" loop exists once.

## Read first
`context/adr/0002-vocabulary-tables.md`, `context/adr/0004-geopackage-single-source.md`; `qskos/utils/gpkg.py`, `qskos/state.py`,
call sites: `grep -rn "gpkg import" qskos/tabs qskos/utils qskos/state.py`.

## Tasks
1. `qskos/utils/gpkg.py`: class `GpkgStore` (pure, no QGIS) holding the path; `ensure_config_table` once in `__init__`; methods
   `vocabularies()`, `vocabulary(scheme)`, `bound_schemes(feature_table)`, `bind()`, `unbind()`, `import_vocabulary(concepts, scheme, lang)`,
   each using one connection (context manager). Module-level helpers that are pure string functions (`norm_path`, `vocab_table_name`,
   source parsing) stay functions.
2. `QskosState.store` (created when the active GPKG changes; `None` without GPKG) replaces passing `active_gpkg_path` around.
3. `qskos/utils/vocabularies.py` (QGIS adapter): `BoundVocabulary` (scheme, table, vocab layer, children_map, labels) and
   `bound_vocabularies(state, feature_layer)` — replaces the three copies of the loop in `tabs/layer.py`
   (`reinitialize_all_annotation_fields_for_layer`), `tabs/symbology.py` (hierarchy merge) and `tabs/lod_export.py` (`_collect_concept_labels`).
4. Move all callers; delete the old free functions (no wrappers left behind).
5. Split `import_vocab_to_gpkg` (82 lines) into table choice, schema check and fill.

## Acceptance criteria
- No `sqlite3` import outside `qskos/utils/gpkg.py`; no `read_config(` calls in `qskos/tabs/`.
- One user action (select a feature layer with two bound vocabularies) opens at most 3 SQLite connections (counted in a test with a
  wrapped `sqlite3.connect`).
- All existing tests pass unchanged in behaviour (test call sites adapted).

## Tests required
`tests/test_gpkg.py` rewritten against `GpkgStore` (all current cases kept, incl. `TestVocabTableIsolation`); unit test for the connection
count; pytest-qgis test for `bound_vocabularies` with two vocabularies.

## Out of scope
Changing table layout or names (ADR-0002); signals between tabs (WP-004).

## Review focus
SQL stays parameterised; identifiers only from the config table or `vocab_table_name`; transaction boundaries of `import_vocabulary`
(a failed import leaves the previous vocabulary intact).

## Human steps
None.
