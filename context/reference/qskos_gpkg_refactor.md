
# qskos Refactoring Specification — GeoPackage-First Architecture

Target version is LTS 3.44.8-Solothurn

## Scope

This document specifies the refactor limited to:

- GeoPackage-first architecture
- Multi-vocabulary binding
- Field rename (remove `skos:` prefixes)
- Persistent `qskos_layer_config` table inside the GeoPackage
- Removal of all deletion-on-uncheck logic

No other features are covered here.

---

## Problem in Current Design

The current plugin design depends on:

- Delimited text layers for vocabularies
- Custom layer properties (`qskos:scheme`, `qskos:binding`)
- QGIS project file for persistence

These properties are stored only in the `.qgs/.qgz` project, not in the data source. Reloading layers from a GeoPackage loses all plugin state.

Goal: make the GeoPackage the authoritative, portable data container.

---

## Target Architecture

After refactor:

- GeoPackage stores:
  - Vocabulary tables
  - Feature layers
  - All binding/configuration metadata
- QGIS project stores nothing essential
- Plugin reconstructs relationships solely from the GeoPackage

---

## qskos_layer_config Table

Create inside every GeoPackage used by qskos:

```sql
CREATE TABLE IF NOT EXISTS qskos_layer_config (
    layer_name   TEXT,
    layer_role   TEXT,     -- 'ConceptScheme' | 'FeatureLayer'
    scheme_uri   TEXT,
    language     TEXT,
    PRIMARY KEY (layer_name, scheme_uri)
);
```

Meaning:

- ConceptScheme → vocabulary table
- FeatureLayer → geometric layer bound to one or more vocabularies

A feature layer has one row per bound vocabulary.

---

## Replace Delimited Text Layers

Remove conversion to delimited text layers entirely.

Vocabulary tables are written directly into the GeoPackage via sqlite3.

### Vocabulary Table Columns

| Old | New |
|-----|-----|
| skos:Concept | Concept |
| skos:prefLabel | prefLabel |
| skos:definition | definition |
| skos:broader | broader |
| skos:inScheme | inScheme |

Provider becomes `ogr`.

---

## Mandatory Plugin State

Track:

```
self.active_gpkg_path
```

All UI logic depends on this. No GeoPackage selected → no functionality.

---

## Vocabulary Import Workflow

1. Select GeoPackage
2. Select RDF/CSV
3. Parse
4. Write vocabulary rows into new GPKG table
5. Insert row into `qskos_layer_config` as `ConceptScheme`
6. Load vocab table as hidden QGIS layer (required for ValueRelation)

### Import Guard

Before import:

```sql
SELECT 1 FROM qskos_layer_config WHERE scheme_uri = ?
```

Prompt before overwrite.

---

## Layer Tab — Multi Vocabulary Binding

Remove vocabulary dropdown and custom property binding.

### UI

```
Feature Layer: [layers from this GPKG only]

Bound Vocabularies:
[list widget]
[Bind Vocab]  [Unbind]
```

### Bind

```sql
INSERT INTO qskos_layer_config
(layer_name, layer_role, scheme_uri)
VALUES (?, 'FeatureLayer', ?)
```

### Unbind

Delete row from config. No attribute deletion dialogs.

---

## Tree View Logic

- Tree shows vocabulary selected in list
- Switching vocab is instant
- Checked state derives from existing fields on the feature layer

---

## Field Creation Changes

Field name remains the Concept URI.

### ValueRelation

| Setting | New |
|--------|-----|
| Layer | GPKG vocab layer |
| Key | Concept |
| Value | prefLabel |
| Filter | "Concept" IN (...) |

Vocab layer must be loaded in QGIS (hidden group).

---

## Remove All Deletion Logic

Delete:

- Uncheck → delete field dialogs
- Unbind → delete field dialogs

Fields must be removed manually by users.

---

## refresh_layer_combos Rewrite

Do not scan QGIS layers.

Use:

```sql
SELECT layer_name FROM qskos_layer_config
WHERE layer_role='FeatureLayer'
```

---

## find_vocab_layer_by_scheme Rewrite

Query config table instead of custom properties.

---

## Symbology Update

For current feature layer:

```sql
SELECT scheme_uri
FROM qskos_layer_config
WHERE layer_name = ?
```

Load hierarchies for all vocabularies and generate rules across all related fields.

---

## Removed Components

- Delimited text layers
- Custom layer properties
- Metadata reliance
- Vocabulary dropdown in layer tab
- All deletion dialogs

---

## Implementation Order

1. Implement `qskos_layer_config` handling
2. Implement GeoPackage selection state
3. Replace vocabulary import to GPKG tables
4. Rewrite binding logic to use config table
5. Rewrite layer refresh logic
6. Rewrite field creation to new column names
7. Remove deletion code
8. Update symbology for multi-vocab

---

## Unchanged from Original Design

- rdflib parsing
- CSV support
- Tree building logic
- ValueRelation principle
- Rule-based symbology concept
- Annotation field storage model

---

## Result

The GeoPackage contains vocabularies, feature layers, and all qskos configuration. Reloading layers reconstructs plugin state without relying on the QGIS project.
