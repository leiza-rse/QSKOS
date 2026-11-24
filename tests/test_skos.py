# test_skos.py
# qskos QGIS Plugin - unit tests for utils/skos.py (SKOS/RDF + CSV parsing).
# skos.py is pure (rdflib + csv only, no QGIS), so it runs without a QGIS
# runtime.

import os
import tempfile

import pytest

from qskos.utils.rdf_model import is_absolute_iri
from qskos.utils.skos import (
    default_scheme_uri, load_skos_source, mint_concept_iris,
    scheme_uri_from_concepts,
)

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

# A mixed source: some concepts have explicit broader, others only rely on
# nested narrower. The narrower-only child must still get its parent.
_MIXED_TTL = """\
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix ex: <http://example.org/> .

ex:scheme a skos:ConceptScheme .
ex:root a skos:Concept ; skos:inScheme ex:scheme ;
    skos:prefLabel "Root"@en .
ex:childA a skos:Concept ; skos:inScheme ex:scheme ;
    skos:broader ex:root ; skos:prefLabel "ChildA"@en .
ex:childB a skos:Concept ; skos:inScheme ex:scheme ;
    skos:prefLabel "ChildB"@en .
ex:root skos:narrower ex:childB .
"""

# A source whose ConceptScheme carries a label but is NOT typed skos:Concept.
# It must not be treated as a concept (only typed concepts are).
_SCHEME_LABEL_TTL = """\
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix ex: <http://example.org/> .

ex:scheme a skos:ConceptScheme ;
    skos:prefLabel "My Scheme"@en ;
    skos:hasTopConcept ex:root .
ex:root a skos:Concept ; skos:inScheme ex:scheme ;
    skos:prefLabel "Root"@en .
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

    def test_per_concept_narrower_fallback(self, tmpdir):
        # childB has no broader but root:narrower childB — its parent must be
        # recovered via per-concept inversion, while childA keeps its explicit
        # broader.
        path = _write(tmpdir, "mixed.ttl", _MIXED_TTL)
        concepts = load_skos_source(path, "rdf", lang="en")
        by_uri = {c["concept"]: c for c in concepts}
        assert by_uri["http://example.org/childA"]["broader"] == \
            "http://example.org/root"
        assert by_uri["http://example.org/childB"]["broader"] == \
            "http://example.org/root"

    def test_scheme_not_treated_as_concept(self, tmpdir):
        # The ConceptScheme carries a prefLabel but is not typed skos:Concept,
        # so it must not be pulled in as a concept.
        path = _write(tmpdir, "scheme.ttl", _SCHEME_LABEL_TTL)
        concepts = load_skos_source(path, "rdf", lang="en")
        uris = {c["concept"] for c in concepts}
        assert uris == {"http://example.org/root"}
        assert "http://example.org/scheme" not in uris


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

    def test_notation_column_is_the_concept_id(self, tmpdir):
        csv_path = os.path.join(tmpdir, "v.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("notation,prefLabel,broader\n")
            f.write("C329A7,Apple,B51DAF\n")
        concepts = load_skos_source(csv_path, "csv", lang="en")
        assert concepts[0]["concept"] == "C329A7"
        assert concepts[0]["broader"] == "B51DAF"

    def test_unsupported_source_type(self, tmpdir):
        with pytest.raises(ValueError):
            load_skos_source("x", "bogus")


SCHEME = "https://example.org/thesaurus"


class TestLocalIds:
    @pytest.mark.parametrize("value, expected", [
        ("https://example.org/a", True),
        ("file:///home/u/vocab.csv", True),
        ("urn:uuid:0f8fad5b-d9cb-469f-a165-70867728950e", True),
        ("C329A7", False),
        ("A:1", False),
        ("0f8fad5b-d9cb-469f-a165-70867728950e", False),
        ("https://example.org/a b", False),
        ("", False),
        (None, False),
    ])
    def test_is_absolute_iri(self, value, expected):
        assert is_absolute_iri(value) is expected

    def test_local_ids_are_appended_to_the_scheme(self):
        concepts = [
            {"concept": "B51DAF", "broader": None, "inScheme": None},
            {"concept": "C329A7", "broader": "B51DAF", "inScheme": ""},
        ]
        minted = mint_concept_iris(concepts, SCHEME)
        assert minted[0] == {"concept": SCHEME + "/B51DAF", "broader": None,
                             "inScheme": SCHEME}
        assert minted[1]["concept"] == SCHEME + "/C329A7"
        assert minted[1]["broader"] == SCHEME + "/B51DAF"
        assert concepts[1]["concept"] == "C329A7", "input must not be mutated"

    def test_iris_are_kept_and_ids_sanitized(self):
        concepts = [
            {"concept": "https://other.org/x", "broader": "https://other.org/y",
             "inScheme": "https://other.org/s"},
            {"concept": " Holz  bearbeitet ", "broader": "a/b#c<d>ä",
             "inScheme": None},
        ]
        minted = mint_concept_iris(concepts, SCHEME + "#")
        assert minted[0] == concepts[0]
        assert minted[1]["concept"] == SCHEME + "#Holz_bearbeitet"
        assert minted[1]["broader"] == SCHEME + "#a%2Fb%23c%3Cd%3E%C3%A4"
        assert all(is_absolute_iri(c["concept"]) for c in minted)

    def test_scheme_from_concepts_ignores_non_iris(self):
        assert scheme_uri_from_concepts(
            [{"inScheme": "my scheme"}, {"inScheme": SCHEME}]) == SCHEME
        assert scheme_uri_from_concepts([{"inScheme": None}]) is None

    def test_default_scheme_uri(self, tmpdir):
        path = os.path.join(tmpdir, "vocab.csv")
        default = default_scheme_uri(path)
        assert default.startswith("file:///") and default.endswith("/vocab.csv")
        assert is_absolute_iri(default)
        assert default_scheme_uri(SCHEME) == SCHEME
