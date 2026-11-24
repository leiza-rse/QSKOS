# ADR-0002: One GeoPackage table per vocabulary

Status: accepted (2026-11-09)

## Context
Table names used to be the scheme URI's last segment. `…/a/scheme` and `…/b/scheme` then shared one table and the second import silently
replaced the first vocabulary (the reported "trees and annotation options disappear" bug). A scheme ending in a feature table's name would
have dropped that table.

## Decision
- New vocabulary tables are named `qskos_vocab_<slug>_<sha1(scheme)[:8]>` (`gpkg.vocab_table_name`).
- Table names are always resolved through `qskos_layer_config` (one `ConceptScheme` row per scheme); names are never derived at lookup time.
  Registered legacy names are kept; a legacy table registered for two schemes is split on re-import.
- Re-import empties and refills the existing table (`DELETE` + `INSERT`) so an open QGIS layer stays valid; callers `reload()` the layer.
- A table that exists without the qskos vocabulary columns is never overwritten (`ValueError`).

## Consequences
Vocabularies are isolated from each other and from user data. Table names are less readable; the UI shows the scheme URI next to them.
