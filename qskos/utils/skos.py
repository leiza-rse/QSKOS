# skos.py
# qskos QGIS Plugin - SKOS Parsing Utilities
# Loads RDF/CSV sources and returns normalised concept dicts.
# Storage to GeoPackage is handled by gpkg.import_vocab_to_gpkg.

import csv
import os
from pathlib import Path
from urllib.parse import quote

from .rdf_model import is_absolute_iri

try:
    from rdflib import Graph, Literal
    from rdflib.namespace import RDF, SKOS
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

    # Discover concept subjects. Prefer subjects explicitly typed skos:Concept
    # (avoids pulling in e.g. ConceptScheme nodes that carry a label); fall
    # back to explicit membership links, then to any subject with a prefLabel
    # as a last resort (covers JSON-LD that omits types and membership).
    def _unique(subjects):
        out = []
        for s in subjects:
            if s not in out:
                out.append(s)
        return out

    seen = _unique(g.subjects(RDF.type, SKOS.Concept))
    if not seen:
        for predicate in (SKOS.inScheme, SKOS.topConceptOf):
            seen.extend(
                s for s in g.subjects(predicate, None) if s not in seen
            )
    if not seen:
        seen = _unique(g.subjects(SKOS.prefLabel, None))

    # Build explicit broader relations first.
    broader_map = {}
    for s in seen:
        for b in g.objects(s, SKOS.broader):
            broader_map.setdefault(s, b)

    # For concepts that still have no broader, invert skos:narrower
    # (parent -> child) per-concept. This handles mixed sources where some
    # concepts use broader and others rely on narrower, without globally
    # disabling the explicit broader relations.
    narrower_inverted = {}
    for parent, child in g.subject_objects(SKOS.narrower):
        narrower_inverted.setdefault(child, parent)
    for s in seen:
        if s not in broader_map and s in narrower_inverted:
            broader_map[s] = narrower_inverted[s]

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

    Expected columns: concept (or notation), prefLabel, definition, broader,
    inScheme.  concept/broader may be local IDs; see mint_concept_iris.
    prefLabel and definition may be pipe-separated multilingual strings
    (e.g. "Reinigung@de|Cleaning@en").
    """
    concepts = []
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row = {k.strip(): v for k, v in row.items()}
            concepts.append({
                # 'notation' is the concept ID column of older QSKOS CSVs
                "concept":    (row.get("concept") or row.get("notation") or "").strip(),
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


# ─── Concept scheme and concept IRIs ─────────────────────────────────────────

def scheme_uri_from_concepts(concepts):
    """The first skos:inScheme of the concepts that is an absolute IRI, or None."""
    for c in concepts:
        if is_absolute_iri(c.get("inScheme")):
            return c["inScheme"]
    return None


def default_scheme_uri(source):
    """Suggested scheme URI for a source without one: a URL as is, a local
    file as its file:/// URI."""
    if is_absolute_iri(source):
        return source
    return Path(os.path.abspath(source)).as_uri()


def mint_concept_iris(concepts, scheme_uri):
    """
    Return the concepts with every local ID (concept, broader) turned into
    '<scheme_uri>/<id>' and inScheme set to scheme_uri where it is no IRI.
    IDs that already are absolute IRIs are kept.  Whitespace in an ID becomes
    '_', everything outside the unreserved URI characters is percent-encoded.
    """
    base = scheme_uri if scheme_uri.endswith(("/", "#")) else scheme_uri + "/"

    def iri(value):
        value = (value or "").strip()
        if not value or is_absolute_iri(value):
            return value
        return base + quote("_".join(value.split()), safe="-._~")

    return [
        dict(c,
             concept=iri(c.get("concept")),
             broader=iri(c.get("broader")) or None,
             inScheme=c.get("inScheme") if is_absolute_iri(c.get("inScheme"))
             else scheme_uri)
        for c in concepts
    ]
