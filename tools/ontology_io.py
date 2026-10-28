"""Shared loading and graph helpers for the QSKOS tools, tests and docs.

Everything here is QGIS-free.  The plugin's bundled rdflib (libs/) is put on
sys.path when rdflib is not installed, so `python tools/main.py` also works
from a plain checkout.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:                                   # prefer an installed rdflib
    import rdflib  # noqa: F401
except ImportError:                    # fall back to the copy bundled in libs/
    sys.path.insert(0, str(ROOT / "libs"))

from rdflib import Graph, Namespace, URIRef                    # noqa: E402
from rdflib.namespace import OWL, RDF, RDFS                    # noqa: E402

ONTOLOGY = ROOT / "ontology" / "qskos.ttl"
SHAPES = ROOT / "ontology" / "shapes.ttl"
QUERIES = ROOT / "ontology" / "queries.rq"
EXAMPLE = ROOT / "ontology" / "example.ttl"
EXAMPLE_VOCAB = ROOT / "ontology" / "example_vocab.ttl"
DOCS = ROOT / "docs"
DIAGRAMS = DOCS / "diagrams"

QSKOS = Namespace("http://archaeology.link/ontology/qskos#")
CRM = "http://www.cidoc-crm.org/cidoc-crm/"
CRMGEO = "http://www.ics.forth.gr/isl/CRMgeo/"

# Namespace -> prefix, for display only (docs, diagrams).
PREFIXES = {
    str(QSKOS): "qskos", CRM: "crm", CRMGEO: "crmgeo",
    "http://www.opengis.net/ont/geosparql#": "geo",
    "http://www.opengis.net/ont/sf#": "sf",
    "http://www.w3.org/ns/oa#": "oa",
    "http://www.w3.org/ns/activitystreams#": "as",
    "http://www.w3.org/ns/dcat#": "dcat",
    "http://purl.org/dc/terms/": "dct",
    "http://www.w3.org/2004/02/skos/core#": "skos",
    "http://www.w3.org/2000/01/rdf-schema#": "rdfs",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf",
    "http://www.w3.org/2001/XMLSchema#": "xsd",
}

# Parent links of the CRM / CRMgeo / DCAT classes the ontology points to, as far
# as needed to walk every QSKOS class up to its root (E1 CRM Entity,
# dcat:Resource).  Taken from CIDOC CRM 7.1.3, CRMgeo 1.2 and DCAT 3; the
# ontology itself deliberately does not repeat them.
CRM_PARENTS = {
    "E77_Persistent_Item": ["E1_CRM_Entity"],
    "E70_Thing": ["E77_Persistent_Item"],
    "E72_Legal_Object": ["E70_Thing"],
    "E18_Physical_Thing": ["E72_Legal_Object"],
    "E71_Human-Made_Thing": ["E70_Thing"],
    "E28_Conceptual_Object": ["E71_Human-Made_Thing"],
    "E89_Propositional_Object": ["E28_Conceptual_Object"],
    "E90_Symbolic_Object": ["E28_Conceptual_Object"],
    "E73_Information_Object": ["E89_Propositional_Object", "E90_Symbolic_Object"],
    "E55_Type": ["E28_Conceptual_Object"],
    "E29_Design_or_Procedure": ["E28_Conceptual_Object"],
    "E53_Place": ["E1_CRM_Entity"],
    "E2_Temporal_Entity": ["E1_CRM_Entity"],
    "E92_Spacetime_Volume": ["E1_CRM_Entity"],
    "E4_Period": ["E2_Temporal_Entity", "E92_Spacetime_Volume"],
    "E5_Event": ["E4_Period"],
    "E7_Activity": ["E5_Event"],
    "E13_Attribute_Assignment": ["E7_Activity"],
}
CRMGEO_PARENTS = {"SP4_Spatial_Coordinate_Reference_System": [CRM + "E29_Design_or_Procedure"]}
DCAT = "http://www.w3.org/ns/dcat#"
DCAT_PARENTS = {"Catalog": ["Dataset"], "Dataset": ["Resource"], "Distribution": [], "Resource": []}


def short(iri) -> str:
    """http://www.w3.org/ns/oa#Annotation -> oa:Annotation (display only)."""
    s = str(iri)
    for ns, p in sorted(PREFIXES.items(), key=lambda kv: -len(kv[0])):
        if s.startswith(ns):
            return f"{p}:{s[len(ns):]}"
    return s


def ontology() -> Graph:
    return Graph().parse(ONTOLOGY)


def with_parent_stub(g: Graph) -> Graph:
    """Ontology plus the CRM/CRMgeo/DCAT parent links above (for path walks)."""
    full = Graph()
    for t in g:
        full.add(t)
    for c, ps in CRM_PARENTS.items():
        for p in ps:
            full.add((URIRef(CRM + c), RDFS.subClassOf, URIRef(CRM + p)))
    for c, ps in CRMGEO_PARENTS.items():
        for p in ps:
            full.add((URIRef(CRMGEO + c), RDFS.subClassOf, URIRef(p)))
    for c, ps in DCAT_PARENTS.items():
        for p in ps:
            full.add((URIRef(DCAT + c), RDFS.subClassOf, URIRef(DCAT + p)))
    return full


def qskos_classes(g: Graph):
    return sorted((s for s in g.subjects(RDF.type, OWL.Class) if str(s).startswith(str(QSKOS))), key=str)


def qskos_properties(g: Graph):
    out = []
    for t in (OWL.ObjectProperty, OWL.DatatypeProperty):
        out += [s for s in g.subjects(RDF.type, t) if str(s).startswith(str(QSKOS))]
    return sorted(out, key=str)


def direct_superclasses(g: Graph, cls):
    return sorted((o for o in g.objects(cls, RDFS.subClassOf) if isinstance(o, URIRef)), key=str)


def subclass_paths(g: Graph, cls, limit=64):
    """Every path cls -> ... -> root, following rdfs:subClassOf (depth-first, sorted)."""
    paths = []

    def walk(node, trail):
        if len(paths) >= limit:
            return
        parents = sorted((o for o in g.objects(node, RDFS.subClassOf) if isinstance(o, URIRef)), key=str)
        if not parents:
            paths.append(trail)
            return
        for p in parents:
            walk(p, trail + [p])

    walk(cls, [cls])
    return paths


def label(g: Graph, node, lang="en") -> str:
    for o in g.objects(node, RDFS.label):
        return str(o)
    return short(node)


def comment(g: Graph, node) -> str:
    for o in g.objects(node, RDFS.comment):
        return str(o)
    return ""
