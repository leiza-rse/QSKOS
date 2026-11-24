# WP-010: Collision-free export IRIs

Status: draft

Tier: strong+review   ·   Depends on: WP-005   ·   Size: M

## Goal
Distinct annotations, objects, layers and features always get distinct IRIs in the export, and IRIs stay stable across exports.

## Read first
`context/adr/0005-export-model.md`; `context/open-questions.md` Q4; `qskos/utils/rdf_model.py` (`slug`, `build_graph` — IRI construction
for object, layer, feature, annotation, geometry, local CRS), `qskos/utils/lod.py` (`_layer_record`), `ontology/shapes.ttl`, `tests/test_export.py`.

## Tasks
1. Apply the decision on Q4 (recommended: readable slug + short hash of the full IRI; layers keyed by GPKG table name, not display name).
2. Split `build_graph` (137 lines) into per-part builders (catalog/dataset, layer, feature, annotation) while changing the IRI scheme.
3. Regenerate `ontology/example.ttl` and `docs/` (`make docs`); update the IRI section of the docs prose (`tools/docs_text.py`).
4. CHANGELOG entry stating that export IRIs changed.

## Acceptance criteria
- Tests: two fields `…/a/color` and `…/b/color` on one layer → two annotations with their own bodies; objects `http://a/x/1` and
  `http://b/y/1` → two objects; two layers with the same display name → disjoint feature IRIs.
- Exporting the same data twice gives byte-identical files.
- SHACL tests pass (with pyshacl installed).

## Tests required
The collision tests above in `tests/test_export.py`.

## Out of scope
New metadata fields; persisting metadata (WP-023).

## Review focus
IRI stability (no counters, no clock); IRIs valid for any user input (object IDs with spaces/umlauts).

## Human steps
Decision Q4 by the export author.
