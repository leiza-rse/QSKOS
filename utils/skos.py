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


def load_skos_source(source_path_or_url, source_type, lang="en"):
    """
    Load SKOS data from an RDF or CSV source.

    Returns a list of dicts with keys:
        concept, prefLabel, definition, broader, inScheme

    Language preference is applied to prefLabel and definition.
    source_type: 'ttl' | 'jsonld' | 'url' | 'csv'
    """
    if source_type in ("ttl", "jsonld", "url"):
        if not RDFLIB_AVAILABLE:
            raise ImportError("rdflib is required to load RDF sources.")
        return _load_from_rdf(source_path_or_url, source_type, lang)
    elif source_type == "csv":
        return _load_from_csv(source_path_or_url, lang)
    else:
        raise ValueError(f"Unsupported source type: {source_type}")


def _load_from_rdf(source, source_format, lang="en"):
    """Load SKOS concepts from an RDF source using rdflib."""
    g = Graph()
    g.parse(source, format=source_format)

    seen = []
    for predicate in (SKOS.inScheme, SKOS.topConceptOf):
        for s in g.subjects(predicate, None):
            if s not in seen:
                seen.append(s)

    concepts = []
    for concept in seen:
        broader = None
        for b in g.objects(concept, SKOS.broader):
            broader = str(b)
            break
        in_scheme = None
        for s in g.objects(concept, SKOS.inScheme):
            in_scheme = str(s)
            break
        concepts.append({
            "concept":    str(concept),
            "prefLabel":  _get_preferred_literal(g, concept, SKOS.prefLabel, lang) or "",
            "definition": _get_preferred_literal(g, concept, SKOS.definition, lang) or "",
            "broader":    broader,
            "inScheme":   in_scheme,
        })
    return concepts


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