# STATUS (2026-11-09)

Present tense, one page max. History goes to `CHANGELOG.md`. Update after every work package.

## Plugin (`qskos/`, QGIS ≥ 3.44, PyQt5)
- Entry `__init__.py` (`qskos` class: dock with five tabs, project read/write hooks, purge of QGIS's own rdflib in favour of `libs/`).
  Shared state `state.py` (`QskosState`: active GPKG, current feature layer, import language, hierarchy cache keyed by GPKG + table).
- Tabs (`tabs/`, one `…Manager` class each, ~120–450 lines): `geopackage` (select GPKG), `vocabulary` (import RDF file/URL or CSV),
  `layer` (bind vocabularies, concept tree, create annotation fields; owns which vocabulary is displayed), `symbology` (rule-based
  renderer from annotations), `lod_export` (DCAT metadata box, per-layer object forms, export one/all).
  Tabs still call each other through the plugin object (`plugin.layer_manager…`) and show dialogs directly (WP-004).
- Utils: `gpkg.py` (pure SQLite: config table, bindings, vocabulary import, ADR-0002; loose functions, one connection per call — WP-002),
  `layers.py` (QGIS: layer path/table, load hidden vocab layers), `annotation.py` (create/reconfigure JSON annotation fields and their
  ValueRelation widget, ADR-0001/0003; `bind_annotation_widgets` runs for every layer added to the project), `fields.py` (lenient value reader), `hierarchy.py`, `skos.py` (rdflib/CSV loaders; local concept IDs minted as `<scheme>/<ID>`),
  `rdf_model.py` + `lod.py` (export, ADR-0005), `logging.py` (`QgsMessageLog`).
- GeoPackage content: `qskos_layer_config` (vocabulary registrations + feature bindings), one `qskos_vocab_*` table per vocabulary
  (legacy last-segment names still read), annotation fields named after concept URIs in the feature tables.
- Known gaps: imports run on the GUI thread (WP-006); `generate_rule_based_symbology` is a 226-line method (WP-003); import languages
  fixed to en/de (Q6); export IRIs can collide (Q4); PyQt5 imports block QGIS 4 (WP-007).

## Export model (`ontology/`, `tools/`, `docs/`)
- `ontology/qskos.ttl` (application ontology + crosswalk), `shapes.ttl` (SHACL), `queries.rq`, `example_vocab.ttl`; `example.ttl` generated.
- `python tools/main.py` (`make docs`) rebuilds example, Mermaid diagrams, `docs/*.md` (GitHub Pages, Jekyll) deterministically.

## Tests and tooling
- `uv run pytest` (`make test`): pure unit tests + export tests (`test_export.py`, unittest style, SHACL tests skip without pyshacl).
- `scripts/run_qgis_tests.sh` (`make test-qgis`): `test_qgis_plugin.py`, `test_qgis_e2e.py` (full tab workflow), `test_qgis_regressions.py`
  (multi-vocabulary, re-import, edit mode, combo re-emit, widget → symbology, legacy text fields) in headless QGIS 3.44 via pytest-qgis.
- CI (`.github/workflows/test.yml`): `pytest` job and `qgis-tests` job (installs QGIS with `scripts/install_qgis_ubuntu.sh`).
- `make next`: work package status (`scripts/wp_status.py`). No linter, no pre-push hook, no plugin zip build yet (WP-001).
