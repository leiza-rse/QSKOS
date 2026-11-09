# Architecture Decision Records (index)

An ADR records one accepted decision and why. Agents read **this index** and only the ADRs their work package lists.
Accepted ADRs are not re-opened by agents; if one blocks you, stop and say so.

| ADR | Rule in one line |
|---|---|
| [0001](0001-annotation-fields-json.md) | Annotation fields are GPKG JSON fields (Map / `JSON` / subType String) holding a list of concept URIs; text fields are only read leniently. |
| [0002](0002-vocabulary-tables.md) | One table per vocabulary, `qskos_vocab_<slug>_<hash>`, resolved only via `qskos_layer_config`; re-import refills, never drops; non-qskos tables are never touched. |
| [0003](0003-field-value-domain.md) | An annotation field named after concept C offers C itself plus all its descendants; symbology uses the same domain. |
| [0004](0004-geopackage-single-source.md) | The GeoPackage is the single source of truth (vocabularies, bindings, annotations); the QGIS project only stores the active GPKG path. |
| [0005](0005-export-model.md) | The export graph is built by the QGIS-free `utils/rdf_model.py`; data uses `qskos:` classes, the DCAT/GeoSPARQL/OA/CRM crosswalk lives only in `ontology/qskos.ttl`. |
| [0006](0006-testing-in-real-qgis.md) | Pure modules are unit-tested without QGIS; everything touching QGIS is tested in real headless QGIS (pytest-qgis) through the real widgets and signals. |
