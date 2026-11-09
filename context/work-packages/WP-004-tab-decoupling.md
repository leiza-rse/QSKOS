# WP-004: Tab decoupling — state signals, `VocabularyImportService`, dialogs at the edge

Status: draft

Tier: strong   ·   Depends on: WP-002   ·   Size: M

## Goal
Tabs no longer call each other through the plugin object; they react to signals of the shared state. Import logic lives in a service
without widgets, so it is testable without the UI and reusable by the background task (WP-006).

## Read first
`qskos/state.py`, `qskos/__init__.py`, `qskos/tabs/geopackage.py` (`load_gpkg`), `qskos/tabs/vocabulary.py` (`on_load_vocab_clicked`,
`extract_or_prompt_scheme_uri`), `qskos/tabs/layer.py` (`on_vocabularies_changed`, `refresh_vocab_list`).

## Tasks
1. `QskosState` becomes a `QObject` with signals `gpkgChanged()`, `vocabulariesChanged()`, `featureLayerChanged(layer)`; setters emit them.
   Keep it importable for unit tests (or split the pure dataclass part).
2. Replace the direct calls (`plugin.layer_manager.…`, `plugin.vocabulary_manager.on_gpkg_selected`, `plugin.lod_export_manager.refresh_forms`,
   `plugin.geopackage_manager.refresh_vocab_list`) with signal connections made in each tab's setup.
3. `qskos/services/vocabulary_import.py`: `VocabularyImportService(store, state).load(source, kind, lang)` → `ImportPreview`
   (concepts, scheme or `None`, exists?) and `.commit(preview, scheme)` → table name; raises typed errors. The tab asks for the scheme URI
   and the replace confirmation and shows messages; the service does parse/import/reload/cache invalidation and emits `vocabulariesChanged`.
4. Same pattern for annotation field creation: `LayerManager.create_annotation_field` keeps only dialogs; logic stays in `utils/annotation.py`.
5. Remove `traceback.print_exc()`; log via `utils/logging.py`.

## Acceptance criteria
- `grep -rn "plugin\.[a-z_]*_manager" qskos/tabs` returns nothing.
- `VocabularyImportService` has unit tests without QGIS widgets (pure part) and a pytest-qgis test; `on_load_vocab_clicked` ≤ 40 lines.
- All e2e and regression tests pass.

## Tests required
Service tests (new), signal test: importing a vocabulary refreshes the Layer tab list without any direct call.

## Out of scope
Threading (WP-006); LOD tab restructuring (WP-005).

## Human steps
None.
