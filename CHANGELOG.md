# Changelog

All notable changes to QSKOS are recorded here. Each entry says **what** changed, **where**, and **why**; the German *Warum* lines are the short rationale for the team.

## [Unreleased] – Fix-forward refactor and agent workflow (branch `refactor/fix-forward`)

### Fixed (each with a regression test in `tests/test_qgis_regressions.py`)
- **Vocabulary tree showed only the top concept** (`utils/layers.py`): the in-memory vocabulary copies used text fields capped at 255 characters, and the provider rejected every concept with a longer definition. The fields are now unlimited, a copy that holds fewer concepts than the table is an error, and capped copies saved by a test build are replaced.
  *Warum:* Beim lokalen Lederthesaurus (CSV) blieb nur „Leather“ im Baum, weil die meisten Definitionen länger als 255 Zeichen sind.
- **Trees and annotation checkboxes went empty while editing** (`utils/layers.py`, `utils/gpkg.py`, `__init__.py`, ADR-0007): on Windows (GDAL 3.13) QGIS's shared GeoPackage connection went stale after an annotation field was added; the vocabulary layers then returned no rows while the feature layer was in edit mode. Trees and widgets now read hidden in-memory copies filled through the plugin's own read-only SQLite access. Copies are refilled after imports and when a saved project restores them; duplicates from a project load are removed after loading finished; old GPKG-backed vocabulary layers in `qskos [internal]` are replaced.
  *Warum:* Beim Annotieren fehlten die Checkboxen und Bäume, solange der Layer im Bearbeitungsmodus war; Ursache war QGIS' geteilte GeoPackage-Verbindung, nicht die Daten.
- **Annotation widgets without options in a new project** (`__init__.py`, `utils/annotation.py`): the widgets read their options from hidden vocabulary layers, which were only loaded once the Layer tab was used. Every vector layer that joins the project now gets its bound vocabularies loaded and its widgets re-pointed (`bind_annotation_widgets`, moved out of the Layer tab). GeoPackages without qskos bindings are only opened read-only (`gpkg.has_qskos_config`) and never written; unchanged widget configs are not re-set, so opening a project does not mark it modified.
  *Warum:* Die Checkboxen fehlten beim ersten Annotieren in einem neuen Projekt und tauchten erst nach Benutzung des Layer-Tabs auf.
- **Vocabularies with local concept IDs could not be exported** (`utils/skos.py`, `tabs/vocabulary.py`, `utils/rdf_model.py`): a CSV with IDs like `C329A7` instead of URIs was stored as is and the export failed with `Invalid line: <C329A7> .`. The import now requires an absolute concept scheme URI (asked for when the source has none, default: the file's `file:///` URI) and mints `<scheme>/<ID>` for every concept/broader that is no URI; a `notation` column serves as the ID when `concept` is missing. The export names a non-IRI value instead of failing in the serializer.
  *Warum:* Lokale Vokabulare mit IDs statt URIs sind der Normalfall; die Nutzer bestimmen über die Scheme-URI, wie die Konzept-URIs gebildet werden.
- **Vocabularies overwrote each other** (`utils/gpkg.py`): table names came from the scheme URI's last segment, so `…/a/scheme` and `…/b/scheme` shared one table; the second import replaced the first and its tree and annotation widget options disappeared. Tables are now `qskos_vocab_<slug>_<hash>` (ADR-0002).
- **Layer tab reset itself** (`tabs/layer.py`) when the layer combo re-emitted the same layer; the displayed vocabulary is now private tab state.
- **Symbology could not read new annotations** (`utils/annotation.py`): text fields made the ValueRelation widget write `{"a","b"}`. Annotation fields are GPKG JSON fields again, with the provider's exact native type — otherwise `commitChanges()` rejects the field, which went unnoticed before (ADR-0001).
- **Ticking a concept committed the user's pending edits**; in edit mode the field now joins the user's edit session.
- **Imported vocabularies were missing from the Layer tab** until the layer was re-selected.
- Field value domain is the concept plus its descendants, so leaf concepts work (ADR-0003).

### Changed
- Merged `rdf-export-dev` into the `qskos/` package layout (`utils/rdf_model.py`, adapted `lod.py`/`lod_export.py`); the LOD Export tab is now covered by the QGIS end-to-end tests.
- Agent workflow: `AGENTS.md`, `context/` with `STATUS.md`, `roadmap.md`, `work-packages/`, `adr/`, `open-questions.md`, `review-checklist.md`; `Makefile` (`test`, `test-qgis`, `docs`, `next`). The earlier `context/assessment.md` and `refactoring.md` are replaced (they marked items resolved that were not); background specs moved to `context/reference/`.

## [Unreleased] – New RDF export model (branch `rdf-export-v4`)

### Summary

The *LOD Export* tab now writes the new QSKOS RDF model: DCAT 3 metadata (`qskos:Catalog`, `qskos:Dataset`, `qskos:Distribution`), GeoSPARQL features and layers that SPARQLing Unicorn can import, Web Annotation annotations, and a CIDOC CRM / CRMgeo superstructure that is stated **once, in the ontology** (`ontology/qskos.ttl`) and not repeated in the exported data.

*Warum:* Das alte Modell (CRM P56 + D9 + `oa:hasBody` = Objekt) passte nicht zum Paper (Abschnitt 3.3), hatte keine DCAT-Metadaten und instabile IDs (`feat_1, feat_2, …` als Zähler).

The change is additive: two existing files are rewritten (see *Changed*), everything else is new. No other tab, no GeoPackage schema and no `__init__.py` is touched.

### Changed (existing files)

#### `utils/lod.py` – rewritten as a thin QGIS adapter
- **What:** The graph is no longer built here. `lod.py` reads QGIS layers/features and converts them into plain records (`LayerRecord`, `FeatureRecord`), then calls `utils/rdf_model.py`. Kept with the same names and signatures: `export_lod_ttl(path, specs, object_namespace, vocab_prefixes)`, `build_lod_graph(...)`, `derive_prefix`, `DEFAULT_OBJECT_NAMESPACE`, `DEFAULT_ANNOTATION_NAMESPACE`. New optional argument `meta` (an `ExportMeta`) on both functions; `build_lod_graph` now returns `(graph, n_features, warnings)` instead of `(graph, n_features)`.
- **What else:** Removed the old model (`crm:P56_bears_feature`, `crmdig:D9_Data_Object`, `oa:motivatedBy <field>`, `oa:Motivation` typing, counter IRIs). Feature IRIs now come from the object ID, the layer name and the `uuid` column (if the layer has one) or the QGIS feature id. The export date/time is read here (`now_stamps()`) and nowhere else.
- **Why / Warum:** Das Modell muss ohne QGIS testbar sein (Tests, Docs, CI). Alles, was `qgis.core` braucht, bleibt in `lod.py`; alles andere wandert nach `rdf_model.py`. Alte Aufrufer funktionieren weiter, nur der Rückgabewert von `build_lod_graph` hat ein drittes Element.
- **Check:** `git diff utils/lod.py` – the first 40 lines (constants, `derive_prefix`) are unchanged in behaviour.

#### `tabs/lod_export.py` – small UI addition and one list fix
- **What (UI):** New group box *Dataset metadata (DCAT)* in the LOD Export tab: *Dataset title* (required), *Licence (IRI)* (editable drop-down, default CC BY 4.0), *Creator* (pre-filled with the QGIS user's full name or login name), and a checkbox *Geometries are in an object-local coordinate system*. Both export buttons (single layer, all layers) read these fields through the new `_export_meta()` and pass an `ExportMeta` to `export_lod_ttl`. New helper `_layer_schemes(layer)` passes the layer's bound vocabulary schemes (`get_bound_vocab_schemes`) so that `qskos:usesVocabulary` and `dct:requires` are correct.
- **What (list fix):** `CRM_CLASSES` now contains only subclasses of `crm:E18_Physical_Thing` and spells CRM 7.1 names with the hyphen (`E22_Human-Made_Object`, `E24_Physical_Human-Made_Thing`, `E25_Human-Made_Feature`). Removed `E39_Actor`, `E53_Place`, `E70_Thing`, `E77_Persistent_Item` (not E18 subclasses).
- **Why / Warum:** DCAT braucht Titel, Lizenz und Ersteller. Die Checkbox ist nötig, weil der Export bisher nur EPSG-CRS-IRIs schreiben konnte; ein objektlokales Koordinatensystem hat keinen EPSG-Code. Die alten Klassennamen (`E22_Human_Made_Object`) gibt es im CIDOC CRM 7.1 nicht; `qskos:MappedObject` ist `E18`, daher passen nur E18-Unterklassen. Die Dropdown-Liste bleibt editierbar.
- **Not changed:** layout of the per-layer forms, object namespace field, file dialogs, messages.

### Added (new files)

| Path | What / Warum |
|---|---|
| `utils/rdf_model.py` | The export model, **QGIS-free**: dataclasses `ExportMeta`, `LayerRecord`, `FeatureRecord`; `build_graph(...)` writes catalogue → dataset → distribution, layers, features, geometries, local CRS, annotations; `serialize_deterministic(...)` sorts statements so the same input gives the same bytes. *Warum:* testbar und wiederverwendbar ohne QGIS; kein Systemzeit-Zugriff, Zeitstempel kommen von außen. |
| `ontology/qskos.ttl` | Application ontology. 11 classes, 5 properties; the **only** place with `rdfs:subClassOf` to DCAT, GeoSPARQL, Web Annotation, SKOS, CIDOC CRM and CRMgeo. *Warum:* Crosswalk einmal in der Ontologie, Daten bleiben schlank. Namespace `http://archaeology.link/ontology/qskos#` ist ein **Platzhalter**. |
| `ontology/shapes.ttl` | SHACL shapes for an export (dataset has title/licence/creator/distribution/layer/vocabulary; WKT starts with a CRS IRI; annotation has target, attribute, body, creator, date). |
| `ontology/queries.rq` | Seven queries: Unicorn SELECT per layer, descendant query, CRM bridge rules (P140/P141; P14/P4 as CONSTRUCT), flat projection, DCAT view, consistency check. Bridges between foreign properties are rules, not axioms. |
| `ontology/example_vocab.ttl` | Synthetic SKOS snapshot for the example (example.org). A real export does not contain this part. |
| `tests/` | `fixture.py` (synthetic export), `test_export.py` (29 tests: model, determinism, Unicorn CRS split, queries, ontology rules, SHACL, QGIS adapter with a stubbed `qgis.core`). |
| `tools/` | `main.py` (orchestrator: `--list --only --from --skip --dry-run --strict`) and its steps: `make_example.py`, `run_tests.py`, `make_diagrams.py` (Mermaid → `.mmd`, SVG, PNG), `make_report.py`, `make_docs.py` with prose in `docs_text.py`; `ontology_io.py` (shared loading), `mermaid-config.json` (fixed seed, so images are byte-stable), `requirements.txt`. |
| `docs/_config.yml`, `docs/_layouts/default.html` | Jekyll shell for GitHub Pages. |
| `CHANGELOG.md` | This file. |

### Generated by `python tools/main.py` (not part of the patch, but tracked)

`ontology/example.ttl`; `docs/index.md`, `docs/model.md`, `docs/vocabulary.md`, `docs/crosswalk.md`, `docs/report.md`; `docs/diagrams/{model-simple,model-cidoc,hierarchy}.{mmd,svg,png}`.
*Warum:* Beispiel, Diagramme und Doku werden aus Ontologie und Builder erzeugt und können daher nicht vom Code abweichen. `tests/` prüft, dass `example.ttl` aktuell ist.

### Model decisions (short)

| Decision | Why / Warum |
|---|---|
| Exported data uses only `qskos:` classes (plus `sf:` geometry type and the chosen E18 class on the object) | Crosswalk nur in der Ontologie; Reasoner bei Bedarf. |
| `qskos:Feature` is an E53 Place (+ `crm:P157` to the object), not E26, no CRMgeo SP6 | E26 hieße „das Polygon IST der Schaden“; SP6 ist auch `geo:Geometry` und kollidiert mit der Disjunktheit zu `geo:Feature`. |
| One `qskos:Annotation` per feature × field, several values = several `oa:hasBody` | Entspricht einer Tabellenzelle; Feldkonzept steht pro Annotation (`qskos:attribute ⊑ crm:P177`). |
| Provenance: `dct:creator` = creator field, `dct:created` = export time, `as:generator` = QSKOS | Web-Annotation-Standard; CRM-Gegenstücke P14/P4 per CONSTRUCT (Q5). |
| WKT is always `"<CRS-IRI> WKT"` | SPARQLing Unicorn liest das CRS aus dem Präfix. Ohne EPSG-Code und ohne Local-CRS-Haken wird ohne Präfix geschrieben (GeoSPARQL nimmt dann CRS84) und eine Warnung in die QGIS-Konsole geschrieben. |
| All features are exported, also those without annotation | Der Layer ist die Dokumentation; vorher fielen unannotierte Features weg. |
| The vocabulary snapshot is not part of the file; schemes are referenced with `dct:requires` | Vokabulare bleiben bei den Herausgebern. |

### Known limits and open points

- Feature IRIs use the QGIS feature id unless the layer has a `uuid` column. Re-creating the GeoPackage rows changes the IRIs.
- The local CRS IRI is built from the data namespace, object ID and layer name; `qskos:definedByRaster` is not filled by the UI yet.
- Ontology namespace is a placeholder; CRMgeo parents should be re-checked against the CRMbase 7.1.x harmonised release.
- Not run here: the plugin inside QGIS (no GUI) and the import into SPARQLing Unicorn; see `PATCH-README.md`.
