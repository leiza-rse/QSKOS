# WP-005: Split the LOD export tab, one spec path

Status: draft

Tier: cheap   ·   Depends on: WP-004   ·   Size: S

## Goal
`tabs/lod_export.py` (447 lines) is below the size limit; the single-layer and export-all buttons build their layer spec through one function.

## Read first
`context/adr/0005-export-model.md`; `qskos/tabs/lod_export.py` (`_build_layer_form`, `_form_spec`, `_export_one_layer`,
`on_export_all_clicked`, `setup_lod_tab`, `refresh_forms`).

## Tasks
1. `qskos/tabs/lod_forms.py`: `LayerObjectForm` widget (object ID, label, CRM class, per-layer export button) with `spec()`.
2. `qskos/tabs/lod_export.py`: metadata box, form list, export actions; `_export_one_layer` uses `form.spec()` (delete the copy of the
   spec dict); `setup_lod_tab`, `refresh_forms`, `on_export_all_clicked` ≤ 50 lines each.
3. Annotation-field discovery and concept labels via `bound_vocabularies` (WP-002).

## Acceptance criteria
- Both files ≤ 300 lines; no function > 50 lines.
- `test_lod_export_produces_valid_turtle` passes; new pytest-qgis test exports a single layer through its form button and gets the same
  annotations as export-all for that layer.

## Tests required
The single-layer export test above.

## Out of scope
Changes to the RDF model (WP-010/011); persisting form values (WP-023).

## Human steps
None.
