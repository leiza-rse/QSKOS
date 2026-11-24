# ADR-0001: Annotation fields are GeoPackage JSON fields

Status: accepted (2026-11-09)

## Context
An annotation field is named after a concept URI and stores the concepts selected for a feature. The first refactor (Oct 2026) switched
from `QVariant.Map` to text fields as "canonical JSON". In real QGIS the ValueRelation widget then writes `{"a","b"}` (not JSON) into
text fields, and the symbology's `array_intersect()` cannot read it. With `QVariant.Map` but no matching `typeName`/`subType`, the GPKG
provider adds the column and then rejects the commit ("field … is not the same"), which went unnoticed because the result was not checked.

## Decision
- Annotation fields are created as `QgsField(uri, QVariant.Map, "JSON", 0, 0, "", QVariant.String)` — the GPKG provider's native JSON type.
- The ValueRelation widget (AllowMulti) stores a list of concept URIs; PyQGIS returns a Python list; default value `array()`.
- `utils/fields.parse_field_value` stays lenient (JSON text, `{a,b}`, `a|b`, bare URI) and symbology splits legacy text values, so data
  written by older builds keeps working. New text annotation fields are never created.

## Consequences
Symbology and export read real arrays. Legacy text fields remain readable; whether to migrate them is open (Q7).
