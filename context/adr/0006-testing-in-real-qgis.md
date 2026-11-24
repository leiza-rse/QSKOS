# ADR-0006: Testing — pure modules without QGIS, the rest in real QGIS

Status: accepted (2026-11-09)

## Context
Bugs in this plugin live at the QGIS boundary: what a widget writes, when a combo re-emits, whether a provider accepts a commit. Tests that set
state or write values directly passed while the plugin was broken.

## Decision
- Pure modules (`utils/fields`, `hierarchy`, `gpkg`, `skos`, `rdf_model`, `state`) have unit tests runnable with `uv run pytest`.
- Code that touches QGIS objects is tested in real headless QGIS via pytest-qgis (`scripts/run_qgis_tests.sh`, CI job `qgis-tests`),
  through the real path: combo → vocabulary list → tree checkbox signals, real `QgsEditorWidgetWrapper` values, real GPKG round trips.
- Every bug fix adds a regression test that fails on the old code (`tests/test_qgis_regressions.py` for QGIS-level bugs).

## Consequences
QGIS-bound tests need a QGIS install (Ubuntu/WSL script provided). The suite does not cover the QGIS desktop main window itself; the
maintainer does a manual check before releases.
