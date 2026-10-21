# skos.py
# qskos QGIS Plugin - SKOS Parsing Utilities
# Loads RDF/CSV sources and returns normalised concept dicts.
# Storage to GeoPackage is handled by gpkg.import_vocab_to_gpkg.

import csv

try:
    from rdflib import Graph, Literal
    from rdflib.namespace import SKOS
    RDFLIB_AVAILABLE = True
except ImportError:
    RDFLIB_AVAILABLE = False


# Source types the UI offers.  'csv' is handled separately (not RDF).
# 'rdf' (local file) and 'url' (remote) let rdflib auto-detect the
# serialization from the source (extension / Content-Type), covering every
# RDF format rdflib supports: Turtle, JSON-LD, RDF/XML, N-Triples, N3,
# TriG, N-Quads, TriX, ...
_FILE_FORMAT = {
    "ttl":     "turtle",
    "jsonld":  "json-ld",
}
_AUTODETECT_TYPES = ("rdf", "url")
_CSV_TYPE = "csv"


def load_skos_source(source_path_or_url, source_type, lang="en"):
    """
    Load SKOS data from an RDF or CSV source.

    Returns a list of dicts with keys:
        concept, prefLabel, definition, broader, inScheme

    Language preference is applied to prefLabel and definition.
    source_type: 'rdf' | 'ttl' | 'jsonld' | 'csv' | 'url'
    """
    if source_type in _FILE_FORMAT or source_type in _AUTODETECT_TYPES:
        if not RDFLIB_AVAILABLE:
            raise ImportError("rdflib is required to load RDF sources.")
        return _load_from_rdf(source_path_or_url, source_type, lang)
    elif source_type == _CSV_TYPE:
        return _load_from_csv(source_path_or_url, lang)
    else:
        raise ValueError(f"Unsupported source type: {source_type}")


def _rdflib_format(source_type, source):
    """
    Map a plugin source_type to the rdflib format string to use.
    'rdf' and 'url' sources have no fixed format — rdflib auto-detects from
    the location (extension / Content-Type) so all RDF serializations work.
    """
    if source_type in _AUTODETECT_TYPES:
        return None
    return _FILE_FORMAT.get(source_type, "turtle")


def _load_from_rdf(source, source_format, lang="en"):
    """
    Load SKOS concepts from an RDF source using rdflib.

    Concept discovery is robust to how the source models things:
      - concepts with an explicit skos:inScheme / skos:topConceptOf, or
      - any subject carrying a skos:prefLabel (covers JSON-LD which often
        omits inScheme/topConceptOf and types).

    Hierarchy: the plugin stores a single 'broader' per concept.  Many
    JSON-LD sources express hierarchy the other way round, as nested
    skos:narrower triples with no skos:broader.  When skos:broader is absent
    we invert skos:narrower to reconstruct the parent for every child.
    """
    fmt = _rdflib_format(source_format, source)
    g = Graph()
    g.parse(source, format=fmt)

    # Discover concept subjects: prefer explicit membership links, fall back
    # to any subject with a prefLabel.
    seen = []
    for predicate in (SKOS.inScheme, SKOS.topConceptOf):
        for s in g.subjects(predicate, None):
            if s not in seen:
                seen.append(s)
    if not seen:
        for s in g.subjects(SKOS.prefLabel, None):
            if s not in seen:
                seen.append(s)

    # Build explicit broader relations; sources (mainly JSON-LD) that only
    # model hierarchy via nested skos:narrower need those inverted instead.
    broader_map = {}
    for s in seen:
        for b in g.objects(s, SKOS.broader):
            broader_map[s] = b
            break
    if not broader_map:
        # Invert skos:narrower (parent -> child) into child -> parent.
        for parent, child in g.subject_objects(SKOS.narrower):
            broader_map.setdefault(child, parent)

    # inScheme: take it from the concept, or a scheme we can derive from the
    # top-level hasTopConcept/ConceptScheme node if the source omits it.
    scheme_uri = _find_scheme_uri(g)

    concepts = []
    for concept in seen:
        in_scheme = None
        for s in g.objects(concept, SKOS.inScheme):
            in_scheme = str(s)
            break
        if in_scheme is None:
            in_scheme = scheme_uri
        concepts.append({
            "concept":    str(concept),
            "prefLabel":  _get_preferred_literal(g, concept, SKOS.prefLabel, lang) or "",
            "definition": _get_preferred_literal(g, concept, SKOS.definition, lang) or "",
            "broader":    str(broader_map[concept]) if concept in broader_map else None,
            "inScheme":   in_scheme,
        })
    return concepts


def _find_scheme_uri(g):
    """
    Best-effort discovery of the ConceptScheme URI from an RDF graph, used to
    backfill missing skos:inScheme on concepts (common in JSON-LD).
    """
    # skos:hasTopConcept: subject is the scheme, object is a top concept.
    for s in g.subjects(SKOS.hasTopConcept, None):
        return str(s)
    # skos:topConceptOf / skos:inScheme: object is the scheme.
    for o in g.objects(None, SKOS.topConceptOf):
        return str(o)
    for o in g.objects(None, SKOS.inScheme):
        return str(o)
    return None


def _get_preferred_literal(graph, subject, predicate, preferred_lang="en"):
    """
    Return the best literal value for a predicate:
    preferred_lang > 'en' > any tagged > untagged > first available.
    """
    candidates = []
    for obj in graph.objects(subject, predicate):
        if isinstance(obj, Literal):
            candidates.append((str(obj), obj.language))
        else:
            candidates.append((str(obj), None))

    for priority in (preferred_lang, "en"):
        for text, lang in candidates:
            if lang == priority:
                return text
    for text, lang in candidates:
        if lang is not None:
            return text
    for text, lang in candidates:
        if lang is None:
            return text
    return candidates[0][0] if candidates else ""


def _load_from_csv(file_path, lang="en"):
    """
    Load SKOS concepts from a CSV file.

    Expected columns: concept, prefLabel, definition, broader, inScheme
    prefLabel and definition may be pipe-separated multilingual strings
    (e.g. "Reinigung@de|Cleaning@en").
    """
    concepts = []
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row = {k.strip(): v for k, v in row.items()}
            concepts.append({
                "concept":    row.get("concept", "").strip(),
                "prefLabel":  _extract_label_by_language(
                                  row.get("prefLabel", "").strip(), lang),
                "definition": _extract_label_by_language(
                                  row.get("definition", "").strip(), lang),
                "broader":    row.get("broader", "").strip() or None,
                "inScheme":   row.get("inScheme", "").strip() or None,
            })
    return concepts


def _extract_label_by_language(label_str, lang="en"):
    """
    Extract the label for a given language from a pipe-separated
    'label@lang|label@lang' string.

    Fallback order: selected lang > en > any tagged > plain text > first part.
    """
    if not label_str:
        return ""

    parts = label_str.split("|")
    lang_map, plain = {}, []

    for part in parts:
        if "@" in part:
            txt, l = part.rsplit("@", 1)
            lang_map[l] = txt
        else:
            plain.append(part)

    if lang in lang_map:
        return lang_map[lang]
    if "en" in lang_map:
        return lang_map["en"]
    if lang_map:
        return next(iter(lang_map.values()))
    return plain[0] if plain else parts[0]