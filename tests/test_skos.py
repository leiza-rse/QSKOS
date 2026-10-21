# test_skos.py
# qskos QGIS Plugin - unit tests for utils/skos.py (SKOS/RDF + CSV parsing).
# skos.py is pure (rdflib + csv only, no QGIS), so it runs without a QGIS
# runtime.

import os
import tempfile

from qskos.utils.skos import load_skos_source

# A minimal SKOS Turtle vocabulary: explicit broader + inScheme.
_TTL = """\
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix ex: <http://example.org/> .

ex:scheme a skos:ConceptScheme .

ex:root a skos:Concept ;
    skos:inScheme ex:scheme ;
    skos:prefLabel "Root"@en, "Wurzel"@de .

ex:child a skos:Concept ;
    skos:inScheme ex:scheme ;
    skos:broader ex:root ;
    skos:prefLabel "Child"@en, "Kind"@de .
"""

# A source that only uses nested narrower (no broader) to test inversion.
_NARROWER_TTL = """\
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix ex: <http://example.org/> .

ex:scheme a skos:ConceptScheme ;
    skos:hasTopConcept ex:root .

ex:root a skos:Concept ;
    skos:prefLabel "Root"@en ;
    skos:narrower ex:child .

ex:child a skos:Concept ;
    skos:prefLabel "Child"@en .
"""

# A JSON-LD vocabulary that omits types and inScheme (only prefLabel),
# exercising the prefLabel-fallback concept discovery.
_JSONLD = """\
{
  "@context": {"skos": "http://www.w3.org/2004/02/skos/core#"},
  "@graph": [
    {"@id": "http://example.org/a", "skos:prefLabel": "A"},
    {"@id": "http://example.org/b", "skos:prefLabel": "B",
     "skos:broader": {"@id": "http://example.org/a"}}
  ]
}
"""


def _write(tmpdir, name, content):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class TestRdfLoad:
    def test_parses_concepts(self, tmpdir):
        path = _write(tmpdir, "v.ttl", _TTL)
        concepts = load_skos_source(path, "rdf", lang="en")
        by_uri = {c["concept"]: c for c in concepts}
        assert "http://example.org/root" in by_uri
        assert "http://example.org/child" in by_uri

    def test_hierarchy_broader(self, tmpdir):
        path = _write(tmpdir, "v.ttl", _TTL)
        concepts = load_skos_source(path, "rdf", lang="en")
        by_uri = {c["concept"]: c for c in concepts}
        assert by_uri["http://example.org/child"]["broader"] == \
            "http://example.org/root"
        assert by_uri["http://example.org/root"]["broader"] is None

    def test_language_selection(self, tmpdir):
        path = _write(tmpdir, "v.ttl", _TTL)
        concepts = load_skos_source(path, "rdf", lang="de")
        by_uri = {c["concept"]: c for c in concepts}
        assert by_uri["http://example.org/root"]["prefLabel"] == "Wurzel"
        # fallback to en when the preferred lang is absent
        de = load_skos_source(path, "rdf", lang="de")
        by_uri_de = {c["concept"]: c for c in de}
        assert by_uri_de["http://example.org/child"]["prefLabel"] == "Kind"

    def test_inverts_narrower_when_no_broader(self, tmpdir):
        path = _write(tmpdir, "n.ttl", _NARROWER_TTL)
        concepts = load_skos_source(path, "rdf", lang="en")
        by_uri = {c["concept"]: c for c in concepts}
        assert by_uri["http://example.org/child"]["broader"] == \
            "http://example.org/root"

    def test_scheme_backfilled_from_has_top_concept(self, tmpdir):
        path = _write(tmpdir, "n.ttl", _NARROWER_TTL)
        concepts = load_skos_source(path, "rdf", lang="en")
        assert all(c["inScheme"] == "http://example.org/scheme"
                   for c in concepts if c["inScheme"])

    def test_jsonld_preflabel_fallback(self, tmpdir):
        path = _write(tmpdir, "v.jsonld", _JSONLD)
        concepts = load_skos_source(path, "jsonld", lang="en")
        uris = {c["concept"] for c in concepts}
        assert uris == {"http://example.org/a", "http://example.org/b"}


class TestCsvLoad:
    def test_parses_and_selects_language(self, tmpdir):
        csv_path = os.path.join(tmpdir, "v.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("concept,prefLabel,definition,broader,inScheme\n")
            f.write("http://example.org/a,Apfel@de|Apple@en,defn,,\n")
        concepts = load_skos_source(csv_path, "csv", lang="en")
        assert concepts[0]["prefLabel"] == "Apple"

    def test_empty_broader_becomes_none(self, tmpdir):
        csv_path = os.path.join(tmpdir, "v.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("concept,prefLabel,definition,broader,inScheme\n")
            f.write("http://example.org/a,Apple,,,\n")
        concepts = load_skos_source(csv_path, "csv", lang="en")
        assert concepts[0]["broader"] is None

    def test_unsupported_source_type(self, tmpdir):
        import pytest
        with pytest.raises(ValueError):
            load_skos_source("x", "bogus")
