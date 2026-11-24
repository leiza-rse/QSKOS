# ADR-0007: Trees and annotation widgets read in-memory copies of the vocabulary tables

Status: accepted (approved by the human, 2026-11-24)

## Context
The concept trees and the ValueRelation annotation widgets read the vocabulary through a QGIS layer. With GeoPackage-backed
vocabulary layers, QGIS shares one connection per GeoPackage file. On Windows (QGIS 3.44.13, GDAL 3.13.2) that connection went stale
after an annotation field was added to a feature table of the same file: while the feature layer was in edit mode, the vocabulary layers
were valid but returned no rows, so trees and annotation widgets were empty. A freshly opened layer and a plain SQLite read of the same
table returned all rows. Not reproducible on Linux with GDAL 3.12.2.

## Decision
- `utils/layers.ensure_vocab_layer_loaded` returns a hidden in-memory layer (provider `memory`) in `qskos [internal]`, filled from the
  GPKG through the plugin's own read-only SQLite connection (`gpkg.read_vocab_rows`). Trees and widgets read only this copy.
- The copy carries the custom property `qskos/vocab_source` = `<normalised gpkg path>|<table>`; it identifies the copy and keys the
  hierarchy cache. `skipMemoryLayersCheck` is set, since the copy is a cache and not user data.
- The GPKG stays the single source of truth (ADR-0004): the copy is refilled after an import (`refresh=True`) and when a saved project
  restores it empty. GPKG-backed vocabulary layers that older builds put into `qskos [internal]` are replaced.
- A project read can create a second copy before the project's own one is restored. Duplicates are removed only after the read has
  finished (`readProject`, one more event-loop tick): QGIS processes events while reading, and removing a layer it is still loading crashes it.

## Consequences
Trees and widgets no longer depend on QGIS's GeoPackage connection. Changes made to a vocabulary table outside the plugin appear after
the next import or project load. The regression tests cannot reproduce the stale connection itself (Linux/GDAL 3.12); they make the
GPKG-backed layers unreadable instead and check that trees and widgets still work.
