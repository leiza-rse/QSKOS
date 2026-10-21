# qskos — Critical Assessment & Improvement Proposals

A candid review of the current architecture, driven by the "Frankenstein"
growth history. The plugin works, but there are real design smells, duplicated
logic, and questionable decisions that would repay a focused refactor. Grouped
by theme; each item says *what's wrong* and *what to do instead*.

> Line numbers refer to the current working tree at the time of writing and
> may drift as the code evolves.

---

## A. The `utils/fields.py` heuristics are a band-aid on a bad data model

**Problem.** `parse_field_value` (utils/fields.py:9) is a cascade of guesses:
"try JSON, try PostgreSQL array, try pipe-separated, else single value." The
very existence of this function means the code doesn't reliably know what shape
annotation values are in. Similarly, `reinitialize_all_annotation_fields_for_layer`
(layer.py:375) guesses field types with magic numbers (`field_type == 11` is
"likely QVariant.Json") and string prefixes. This is whack-a-mole over an
ill-defined storage format.

**Root cause.** The annotation field is `QVariant.Map` with a `QgsDefaultValue("array()")`
default, but storage/round-tripping through GeoPackage mutates that into
whatever OGR happens to give back (string, JSON, array, ...). The plugin never
*decides* the canonical serialization, so every consumer re-guesses.

**Fix.** Decide a single canonical on-disk representation (e.g. a delimited
string or JSON array), and centralise encode/decode in **one** module. Have a
single place that converts a stored value to a `list[str]` and back. Delete
`parse_field_value`'s guessing and the magic-number type checks. The field-type
sniffing for "is this an annotation field" should not rely on type; it should
use the config table (which fields belong to which bound vocab), which the
plugin already has.

---

## B. Duplicated, drifting logic in `tabs/layer.py`

**Problem.** `layer.py` is ~612 lines — by far the largest file — and contains
obvious copy-paste with silent drift:

- `_get_concept_label_from_vocab_layer` (layer.py:446) vs
  `_get_concept_label_from_tree` (layer.py:457) both do "find a label for a
  concept URI" two different ways.
- `_concept_belongs_to_vocab` (layer.py:436) does a per-concept feature query on
  the vocab layer — O(N) queries, one per concept, every time.
- The ValueRelation `config` dict is built twice almost identically:
  `create_annotation_field` (layer.py:544) and `_reconfigure_annotation_field`
  (layer.py:493).
- `reinitialize_all_annotation_fields_for_layer` re-implements the whole "find
  annotation fields + attach ValueRelation" workflow a third time.

**Fix.** Extract a single `AnnotationFieldManager` (or a set of functions in
`utils/fields.py`) that owns:
1. detecting annotation fields from the config table,
2. building the ValueRelation config for a given (feature_layer, vocab_layer, concept),
3. encode/decode.

Then `create_annotation_field` and the "reconfigure on load" path both call it.
Replace per-concept feature queries with a single read of the hierarchy index +
vocab layer into a URI→label dict once.

---

## C. Feature queries looped per-concept — O(features × concepts)

**Problem.** Symbology (symbology.py:195) iterates `layer.getFeatures()` once per
annotation field, and inside each feature iterates parsed values. Ancestor
walking is per-URI. On large layers this is quadratic-ish and re-reads the same
features repeatedly. It's functional for small research datasets, but it will
not scale. The LOD export (utils/lod.py:184) does the same — one `getFeatures()`
pass per layer (that part is fine), but re-parses values per field per feature.

**Fix.** Do a single pass over features, build one `concept_uri -> set(features)`
inverted index, then derive per-field grouped values from it. Read features once,
not once-per-field.

---

## D. Shared mutable global state on the plugin object

**Problem.** `__init__.py` exposes a grab-bag of mutable state
(`current_feature_layer`, `current_vocab_layer`, `current_vocab_scheme`,
`selected_language`, `hierarchy_cache`, ...) that every tab reads *and writes*
directly (`self.plugin.current_vocab_layer = ...` from inside layer.py:419). This
makes data flow implicit and hard to reason about; tab managers reach into each
other's state through the plugin object. It's the classic "global state" smell.

**Fix.** Introduce a small typed **state object / dataclass** (e.g.
`QskosState`) that managers are handed, with explicit getters/setters and
change signals. Managers should receive dependencies explicitly rather than
fishing them off `self.plugin`. This also makes the code testable without
constructing a fake plugin.

---

## E. The hierarchy "cache" is a misleading name for a recompute-every-time

**Problem.** `get_hierarchy_for_layer` (__init__.py:64) caches by `layer.id()`
but layer IDs change on project reload — which is *why* it works, but it means
the cache is invalidated constantly. In practice `build_hierarchy_index` scans
every feature of the vocab layer (`for feat in vocab_layer.getFeatures()`) and
is re-run frequently (symbology calls it per vocab per generation; the LOD tab
re-collects all concept labels on every tab open — lod_export.py:237). For large
vocabularies this is repeated full-table scans.

**Fix.** Cache keyed on (gpkg path, table name, a cheap content hash / modified
timestamp) instead of volatile layer id. Build the index once per
vocab-import and invalidate only on import. Consider storing the hierarchy in
the GeoPackage config rather than recomputing.

---

## F. Symbology rule expression can blow up

**Problem.** Each rule's filter is `" OR ".join(array_contains(...) for u in all_desc)`
(symbology.py:245). For a concept with thousands of descendants, that's a
thousands-term expression embedded in the renderer — slow to evaluate and ugly
to maintain. The "All" rule duplicates the full descendant list again.

**Fix.** Use the native QGIS relationship: a rule can match by testing
`concept IN (subtree)` — but better, since the field *stores* URIs, prefer a
single `array_intersect`/`array_contains_any` expression against the descendant
list rather than `OR`-chaining individual `array_contains`. Also deduplicate:
the "group", "All", and "child" rules currently re-list the same descendant sets
at multiple levels, which is redundant.

---

## G. Annotation values in `QVariant.Map` is an odd choice

**Problem.** `create_annotation_field` (layer.py:524) creates a `Map`-typed
field but then relies on a `QgsDefaultValue("array()")` and multi-select
ValueRelation to fill it with an array of URIs. Map is a key-value type; using
it to hold an array of URIs is semantically wrong and is the reason storage
round-tripping produces unpredictable shapes (see A). StringList or a plain
text/JSON field would be clearer.

**Fix.** Use a field type that matches the data (a list of URIs). Decide the
canonical serialization (JSON string or StringList), and let OGR round-trip it
consistently. This removes most of section A's guesswork at the source.

---

## H. `selected_language` is a plugin-global that should be per-vocabulary

**Problem.** `self.plugin.selected_language` (__init__.py:48) is a single global
set in the vocabulary tab. It's used at import time to bake one language into
the vocab table's `prefLabel`. That's fine for import, but the global lives on
the plugin object and reads as if the language is a UI-wide setting, while each
vocab actually stores its own language in the config (`find_vocab_language`).
The design is half-global, half-per-vocab.

**Fix.** Make language purely an import-time argument passed to
`import_vocab_to_gpkg`; drop the global. Reading labels later should use the
stored per-vocab language. This removes a footgun (two vocabularies in different
languages can't both be handled correctly by one global).

---

## I. Testability is blocked by hard Qt/QGIS coupling

**Problem.** `utils/gpkg.py` imports `from qgis.core import QgsVectorLayer,
QgsProject` at module top (gpkg.py:10) and `utils/lod.py` imports QGIS too.
The refactor doc (context/qskos_gpkg_refactor.md) claims separation of "pure
data logic" for testability, but the pure modules still pull in QGIS and Qt at
import time. There is no test suite at all in the repo.

**Fix.** Split the *actually pure* parts (SQLite access, SKOS parsing, hierarchy
index math, LOD graph building) into modules with **no QGIS imports**, keeping
QGIS adapters thin. Add pytest unit tests for those pure layers (the repo is
currently entirely untested, which is risky for a research tool people cite).
The good news: the SKOS/RDF parsing (`utils/skos.py`) is already pure and is a
perfect first target for unit tests, especially now that it handles multiple
serializations and heterogeneous sources.

---

## J. Error handling: broad `except: pass` / `continue` swallow real bugs

**Problem.** Multiple spots catch everything and continue silently
(e.g. `_load_tree_for_item`'s bare `except Exception: self._clear_tree()`
layer.py:141; `reinitialize...`'s `except: continue` layer.py:432;
`_collect_concept_labels`'s `except: continue` lod_export.py:239; various
`except: pass`). This hides genuine failures behind "nothing happened in the
UI."

**Fix.** Log failures (QGIS has `QgsMessageLog`) with context instead of
swallowing. Only catch the specific exception you can handle. This is
especially important in symbology and LOD export, where silent skips of a vocab
produce subtly wrong output.

---

## K. Misc smaller nits

- **Bundled `libs/` hack** (__init__.py:8-31): purging `rdflib` from
  `sys.modules` to force the bundled copy is fragile and version-sensitive.
  Document it better or pin and test against the QGIS Python environment.
- **`print()` for logging** throughout — use `QgsMessageLog` / `QgsLogger`.
- **Redundant re-imports**: `scheme_exists_in_gpkg` and `find_vocab_table_for_scheme`
  both re-read the whole config table; the config is tiny so this is cheap, but
  it's called in hot-ish loops. `read_config` itself opens a new sqlite
  connection on every call.
- **`random` colours** for symbology (symbology.py:74) — random colours change
  every generation and aren't reproducible. Derive a stable colour from the
  concept URI hash for consistent, deterministic styling.
- **`while current and ...` ancestor walk** in symbology (symbology.py:201) only
  takes `parents[0]` — for concepts with multiple `broader` parents (polyhierarchical
  SKOS), it silently drops all but one parent. This is a correctness bug for
  polyhierarchy.

---

## L. New-code observations (RDF ingestion & LOD namespace)

These concern the recently added/expanded features and are *lower severity*
— they are improvements to otherwise welcome functionality.

- **`utils/skos.py` "no `broader` found" heuristic can misfire.** The loader
  falls back to inverting `skos:narrower` *only if* no `broader` at all was found
  across the whole graph (`if not broader_map:` at skos.py:97). A mixed source
  (some concepts with `broader`, others relying on `narrower`) silently drops
  the parent for the `narrower`-only concepts. Prefer per-concept fallback:
  if a concept has no `broader`, look for an inverted `narrower` for *that*
  concept rather than disabling inversion globally.
- **Concept discovery via any `skos:prefLabel` subject is broad.** It can pull
  in non-concept nodes (e.g. a `ConceptScheme` that itself carries a label) and
  treat them as concepts. Consider filtering to subjects typed `skos:Concept`
  when type triples exist, keeping prefLabel-fallback only as a last resort.
- **Stale header comment in `tabs/lod_export.py` (line 11-12)** still says
  "Object namespace and annotation namespace ... are not user-configurable",
  but the object namespace is now a user-editable field. Update the comment to
  match behaviour.
- **Object namespace is UI-only, not persisted.** The namespace input
  (lod_export.py:69) isn't stored in the GeoPackage config, so it's lost when
  the project/GPKG is reopened. For a portability-focused plugin, persisting the
  institution namespace in `qskos_layer_config` would be consistent with the
  "single source of truth" principle.
- **Two LOD export entry points duplicate the file-dialog + export flow**
  (`_export_one_layer` and `on_export_all_clicked`). Extract the shared
  "validate namespace → choose path → export → report" sequence.

---

## Suggested prioritisation

1. **Fix the data model** (A + G): decide canonical annotation value storage →
   kills the guessing cascade and most of layer.py's re-init hack.
2. **Extract `AnnotationFieldManager`** (B) to remove the triple duplication.
3. **De-QGIS the pure utils** and add tests (I) — biggest long-term win for a
   plugin that will keep growing; start with `utils/skos.py`.
4. **Cache hierarchy properly** (E) and **single-pass feature reads** (C).
5. **Deterministic symbology + polyhierarchy handling** (F + K-colour/K-parent).
6. **Replace global state with a state object** (D), then tighten error handling (J).
7. **Tighten the RDF heuristics** (L) so the new flexible ingestion doesn't
   silently mis-parse heterogeneous sources.
