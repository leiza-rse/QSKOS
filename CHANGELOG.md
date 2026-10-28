# Changelog

All notable changes to QSKOS are recorded here. Each entry says **what** changed, **where**, and **why**; the German *Warum* lines are the short rationale for the team.

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
