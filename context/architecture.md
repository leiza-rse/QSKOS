# qskos — Architecture Overview

This document describes the high-level architecture of the **qskos** QGIS plugin.
It is intended as a basis for a paper: it explains *how the plugin works* and
*what it contributes* on top of existing QGIS capabilities — not at the level of
individual functions, but in terms of the overall design decisions.

---

## 1. The Problem

Researchers annotate geographic features (polygons, points, lines) with semantic
labels drawn from *controlled vocabularies*. The challenge is that semantic
annotations only add value if they are:

- **standardised** — labels come from an authoritative vocabulary, not free text;
- **portable** — the annotations travel with the data, not locked into one
  application's project file;
- **machine-readable** — they can be exported into the broader Semantic Web /
  Linked Open Data (LOD) ecosystem.

The plugin's role is to make these three properties achievable inside the QGIS
desktop GIS, reusing as much of QGIS's native machinery as possible and adding
only the semantic glue on top.

---

## 2. Core Design Decision: The GeoPackage as Single Source of Truth

The central architectural decision is a **GeoPackage-first design**. All plugin
state lives *inside the GeoPackage* (`.gpkg`), which is the same file that
already holds the geographic data. The QGIS project file (`.qgs`/`.qgz`) is
deliberately not used to store anything essential; it only remembers the path to
the active GeoPackage.

The GeoPackage is a portable SQLite container. The plugin stores three kinds of
things in it:

1. **Feature layers** — the actual geographic data the user wants to annotate.
2. **Vocabulary tables** — non-spatial attribute tables, one per imported
   vocabulary, with columns `concept`, `prefLabel`, `definition`, `broader`,
   `inScheme`.
3. **A configuration table** (`qskos_layer_config`) — a small registry that
   records, per layer:
   - its *role* (is it a `FeatureLayer` or a `ConceptScheme`/vocabulary table?),
   - the *concept-scheme URI* it belongs to,
   - and (for feature layers) which vocabularies are **bound** to it.

This means that reopening a GeoPackage in any project (or on any machine)
reconstructs the entire semantic setup without needing a special project file.
The GeoPackage becomes authoritative and self-contained.

---

## 3. Vocabulary Ingestion: RDF, Any Serialization

The plugin accepts vocabularies as SKOS in a wide range of forms:

- **Local RDF files** — the serialization is auto-detected by `rdflib` from the
  file extension, so Turtle, JSON-LD, RDF/XML, N-Triples, N3, TriG, and others
  all work without the user choosing a format.
- **Remote URLs** — the vocabulary is fetched over HTTP(S); `rdflib`
  auto-detects the format from the served `Content-Type`.
- **CSV** — a tabular mirror of a SKOS vocabulary (columns `concept`,
  `prefLabel`, `definition`, `broader`, `inScheme`).

The RDF loader (`utils/skos.py`) is deliberately tolerant of how different
sources model the data, because real-world vocabularies differ:

- **Concept discovery** prefers explicit membership links
  (`skos:inScheme` / `skos:topConceptOf`), but falls back to "any subject with a
  `skos:prefLabel`" — important because JSON-LD often omits membership/type
  triples.
- **Hierarchy reconstruction** prefers explicit `skos:broader` links, but where
  a source expresses the hierarchy the other way round (nested `skos:narrower`
  with no `broader`), the plugin inverts `narrower` to recover each concept's
  parent.
- **Scheme URI backfilling** recovers a missing `skos:inScheme` from
  `skos:hasTopConcept` / `topConceptOf` / other `inScheme` statements in the
  graph.

The result is a normalised set of records — concept URI, preferred label,
definition, broader, inScheme — that is written into the GeoPackage.

---

## 4. What the Plugin Reuses from QGIS

A deliberate goal is to build on top of QGIS's native, standards-based features
rather than re-implementing GIS functionality. The plugin uses QGIS for:

| Concern | QGIS mechanism used |
|---------|---------------------|
| Reading & writing geographic data | GeoPackage via the OGR provider |
| Loading vocabulary tables | Vector layers loaded from the GPKG via OGR (hidden in an internal layer group) |
| Concept selection in forms | **Value Relation** editor widgets on annotation fields |
| Storing annotation values | Map-type attribute fields on the feature layer |
| Visualising annotations | **Rule-based symbology** (`QgsRuleBasedRenderer`) |
| Representing geometries in LOD | **GeoSPARQL** WKT literals derived from QGIS geometries |

The plugin *orchestrates* these native pieces; it does not replace them.

---

## 5. The Annotation Data Model

The plugin maps semantic concepts onto the relational structure that QGIS
understands natively. This is the key conceptual contribution.

- Each **concept URI** in a vocabulary becomes an **attribute field** on the
  feature layer. The *field name* is the concept URI.
- The field's **Value Relation widget** is configured to let the user pick any
  *descendant* of that concept from the bound vocabulary. QGIS displays the
  human-readable `prefLabel` while storing the concept URI.
- The **value stored in the field** is therefore a set of concept URIs — the
  specific semantic labels assigned to that feature.

In other words, the plugin encodes a *semantic hierarchy* using two ordinary
relational mechanisms that QGIS already supports: columns for concepts, and
Value Relation widgets for controlled pick-lists that respect the hierarchy via
filter expressions.

---

## 6. The Hierarchy: from RDF to Trees to Symbology

The vocabulary arrives as an RDF/SKOS source (or a CSV mirror of it). The plugin
handles the hierarchy in several stages, all built on a single in-memory index:

1. **Ingest.** `rdflib` parses the source; concepts, preferred labels,
   definitions, and parent (`broader`, or inverted `narrower`) relations are
   extracted into normalised records.
2. **Materialise.** The records are written into the GeoPackage as an attribute
   table (with the `broader` column encoding the parent links).
3. **Index.** The parent/child links are read back into a cached
   `children_map` / `concept_labels` structure — effectively a precomputed
   adjacency list of the concept hierarchy (see `utils/hierarchy.py`).
4. **Browsing.** The same index drives the plugin's concept tree in the UI, so
   users can explore and select concepts for annotation.
5. **Rendering.** The index is walked again to derive, for any concept, the set
   of all its descendants — which is exactly what is needed to build symbology
   rules (and Value Relation filters).

This single shared hierarchy index is what lets the plugin treat "browse the
vocabulary", "pick a descendant", and "colour by a concept subtree" as the same
underlying operation.

---

## 7. Hierarchical Symbology Generation

The symbology is the feature most likely to be described in the paper, so it is
worth spelling out the approach.

Given an annotated feature layer, the plugin builds a **rule-based renderer** —
a standard QGIS construct that evaluates a hierarchy of boolean filter
expressions to decide how to draw each feature. The plugin generates this rule
tree automatically from the annotations:

1. **Detect annotation fields.** Any field whose name is a known concept URI
   from a bound vocabulary is treated as an annotation field.
2. **Merge vocabularies.** If several vocabularies are bound to the layer, their
   hierarchy indices are unioned, so a feature can be styled consistently across
   all of them at once.
3. **Collect present values.** The plugin scans the features to find which
   concept URIs are actually used in each field.
4. **Close under ancestors.** For every used leaf concept, the plugin walks back
   up the hierarchy and includes the intermediate ancestors, so the styling
   reflects the full path from the field's root concept down to the annotated
   leaf.
5. **Emit rules.** For each field, a nested group of rules is created. Each rule
   is a QGIS expression of the form `array_contains(<field>, '<concept>')`
   testing whether a feature carries that concept or any of its descendants. The
   nested rules mirror the concept hierarchy: a group rule for the field, child
   rules for the concepts actually present, and an "else" rule for unannotated
   features. Each rule gets a distinct symbol/colour.

The result is that QGIS's *standard* rule-based renderer is populated with a
*generated* rule tree that directly mirrors the semantic structure of the
annotations. The plugin adds the intelligence (interpreting the semantic
hierarchy, closing it under ancestors, and emitting the right filter
expressions); QGIS provides the rendering.

---

## 8. Linked Open Data Export

As a final step, the plugin can project the annotations into the Semantic Web.
It builds an `rdflib` graph where each feature layer (with a user-supplied Object
ID) becomes a CIDOC-CRM entity. The user configures an **object namespace**
(their institution's URI prefix, applied to all layers); each layer's Object ID
is appended to it to form the entity's subject URI. The mapping is:

- the **annotation field** (the concept that motivated the annotation) maps to
  `oa:motivatedBy`,
- the **selected concept values** map to `oa:hasTarget`,
- the feature's **geometry** is emitted as a GeoSPARQL WKT literal,
- each annotation node is typed as a `crmdig:D9_Data_Object` (and `oa:Annotation`),
  linked to the object via `crm:P56_bears_feature`.

Layers sharing the same Object ID merge into one object (same subject URI) in
the output. The graph is serialised to Turtle. Again, the plugin leans on
existing machinery (`rdflib` for graph handling, QGIS for geometry
serialisation) and contributes the mapping from the plugin's internal annotation
model to established ontologies.

---

## 9. Module Layout

```
qskos/
├── __init__.py          plugin lifecycle: dock widget, tab wiring, shared state,
│                        hierarchy cache, project persistence hooks
├── tabs/                one manager per dock-widget tab (UI logic only)
│   ├── geopackage.py    select the active GeoPackage
│   ├── vocabulary.py    import RDF/CSV (local or remote) into the GPKG
│   ├── layer.py         bind vocabularies, browse the concept tree,
│   │                    create annotation fields
│   ├── symbology.py     generate rule-based symbology
│   └── lod_export.py    per-layer LOD export forms + object namespace
├── utils/               pure data logic (no UI) — separated from tabs for testability
│   ├── gpkg.py          all GeoPackage/SQLite read-write + shared constants
│   ├── skos.py          rdflib/CSV parsing into normalised concept records
│   ├── hierarchy.py     concept-tree building + hierarchy index + descendant BFS
│   ├── fields.py        annotation value parsing
│   └── lod.py           LOD/RDF graph construction
└── libs/                bundled pure-Python deps (rdflib + its deps) so the
                         plugin works without a separate pip install
```

The clean separation between `tabs/` (Qt/QGIS UI) and `utils/` (pure data logic)
means the heavy lifting — parsing, storage, hierarchy computation, rule
generation inputs, and RDF construction — is independent of the widget layer and
testable in isolation.

---

## 10. What the Plugin Adds (Summary)

QGIS already provides the underlying primitives: GeoPackage storage, vector
layers, Value Relation widgets, attribute fields, rule-based symbology, and
geometry access. **qskos does not reinvent these.** Its contribution is the
*semantic interpretation and orchestration* that connects them:

- **A controlled-vocabulary import & persistence pipeline** that turns SKOS/RDF
  (any serialization, local or remote) into GeoPackage tables and keeps a
  registry of them (`qskos_layer_config`).
- **Robust hierarchy extraction** from heterogeneous RDF sources (broader vs
  inverted narrower, scheme backfilling).
- **A binding model** that links one feature layer to many vocabularies.
- **A mapping from concept hierarchies to QGIS fields and pick-lists**: concept
  URI → field name, descendant set → Value Relation filter.
- **A rule-tree generator** that translates the semantic hierarchy and the
  actual annotations into a working QGIS rule-based renderer.
- **An RDF/LOD projection** that re-expresses the annotation model using
  standard ontologies (CIDOC-CRM, oa, GeoSPARQL, crmdig) under a
  user-configurable institution namespace.
- **Portability**, by making the GeoPackage — not the QGIS project — the single
  source of truth.

In short, the plugin treats QGIS as a rich substrate and adds the "semantic
layer" that understands controlled vocabularies, their hierarchies, and their
meaning in the Linked Data world.
