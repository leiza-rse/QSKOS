# ADR-0005: RDF export model

Status: accepted (merged from `rdf-export-dev`, 2026-11-09; details of IRIs and metadata are open: Q1–Q5)

## Context
The old export (CRM P56 + D9 + `oa:motivatedBy`, counter IRIs) did not match the paper (section 3.3) and had no dataset metadata.
Full rationale: `CHANGELOG.md` § "New RDF export model".

## Decision
- `utils/rdf_model.py` (no QGIS) builds the graph from plain records (`ExportMeta`, `LayerRecord`, `FeatureRecord`); `utils/lod.py` is the
  only QGIS adapter; `tabs/lod_export.py` only collects input.
- Data uses `qskos:` classes; the crosswalk to DCAT 3, GeoSPARQL, Web Annotation, SKOS, CIDOC CRM/CRMgeo is stated once in `ontology/qskos.ttl`.
- One `qskos:Annotation` per feature × field: field concept → `qskos:attribute`, values → `oa:hasBody`, feature → `oa:hasTarget`.
- Output is deterministic (no clock reads inside the model); `docs/` and `ontology/example.ttl` are generated from ontology + builder.

## Consequences
The model is testable without QGIS (`tests/test_export.py`). Changes to the model go through the ontology, shapes and generated docs together.
