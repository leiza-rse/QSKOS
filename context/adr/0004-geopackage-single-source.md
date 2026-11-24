# ADR-0004: The GeoPackage is the single source of truth

Status: accepted (documents the existing design; see `context/reference/architecture.md` § 2)

## Context
Annotations must travel with the data, not with one QGIS project file.

## Decision
- Vocabularies are attribute tables in the GPKG; bindings (feature table ↔ scheme) and vocabulary registrations live in `qskos_layer_config`.
- Annotation values live in the feature tables' annotation fields (ADR-0001).
- The QGIS project stores only the active GPKG path (`qskos/active_gpkg`); editor widget configs are re-derived from the GPKG when a feature
  layer is selected (`LayerManager.reinitialize_all_annotation_fields_for_layer`), and carry `LayerName`/`LayerSource` for re-resolution.
- Vocabulary layers are loaded into the hidden group `qskos [internal]`.

## Consequences
A GPKG opened in a new project works after selecting it in the plugin. Anything the plugin needs must be readable from the GPKG alone.
