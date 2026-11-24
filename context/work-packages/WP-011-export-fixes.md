# WP-011: Export fixes — vocabulary usage, metadata copy, serialisation, licence check

Status: draft

Tier: cheap   ·   Depends on: WP-005   ·   Size: S

## Goal
The export states only the vocabularies a layer really uses, never mutates its inputs, serialises once (unless Q10 says otherwise),
and rejects invalid licence IRIs before building the graph.

## Read first
`context/open-questions.md` Q5, Q9, Q10; `qskos/utils/lod.py` (`_layer_record`, `build_lod_graph`, `export_lod_ttl`),
`qskos/utils/rdf_model.py` (`serialize_deterministic`, `is_iri`), `qskos/tabs/lod_export.py` (`_layer_schemes`, `_export_meta`).

## Tasks
1. Q5: `vocab_schemes` = schemes of the vocabularies the layer's annotation fields belong to (via `bound_vocabularies`); remove the
   fallback to all `vocab_prefixes`; `_layer_schemes` logs instead of swallowing errors.
2. Q9: `build_lod_graph`/`export_lod_ttl` work on `dataclasses.replace(meta, …)`; the caller's `ExportMeta` is unchanged afterwards.
3. Q10: per the decision, serialise once with rdflib's Turtle serializer or keep the sort with a comment explaining why.
4. `is_iri` checks a real IRI (scheme + no whitespace/`<>"{}|\^\``), used for licence and object IDs.

## Acceptance criteria
- Test: layer with fields from one of two GPKG vocabularies → `usesVocabulary` lists only that one.
- Test: the same `ExportMeta` used twice → caller's object unchanged, second export has its own timestamps.
- Test: licence `https://example.org/a b` is rejected in `_export_meta`.
- `make docs` leaves `git status` clean (or the regenerated files are committed with the change).

## Tests required
The three tests above (`tests/test_export.py`, pytest-qgis for `_export_meta`).

## Out of scope
IRI scheme (WP-010).

## Human steps
Decisions Q5, Q9, Q10 by the export author.
