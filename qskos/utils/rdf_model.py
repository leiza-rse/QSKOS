# rdf_model.py
# qskos QGIS Plugin - RDF export model (QGIS-free)
#
# Builds the QSKOS export graph (DCAT 3 + GeoSPARQL + Web Annotation, with the
# CIDOC CRM crosswalk living in ontology/qskos.ttl, NOT in the data) from plain
# Python records.  Nothing in here imports qgis.*, so the model can be tested
# and run outside QGIS (see tests/ and tools/).  utils/lod.py is the thin QGIS
# adapter that turns layers/features into the records defined below.
#
# Design rule: the exported data carries only qskos: classes (plus the sf:
# geometry type and the CRM class chosen for the physical object).  Every
# superclass (dcat:*, geo:*, oa:*, crm:*, skos:*) is asserted solely by the
# application ontology via rdfs:subClassOf.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, RDF, RDFS, SKOS, XSD

NS_QSKOS = Namespace("http://archaeology.link/ontology/qskos#")
NS_CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
NS_GEO = Namespace("http://www.opengis.net/ont/geosparql#")
NS_SF = Namespace("http://www.opengis.net/ont/sf#")
NS_OA = Namespace("http://www.w3.org/ns/oa#")
NS_AS = Namespace("http://www.w3.org/ns/activitystreams#")
NS_DCAT = Namespace("http://www.w3.org/ns/dcat#")

DEFAULT_OBJECT_NAMESPACE = "http://w3id.org/archlink/objects/"
DEFAULT_DATA_NAMESPACE = "http://data.archaeology.link/data/qskos/"
GENERATOR_IRI = URIRef("https://github.com/leiza-rse/QSKOS")
TURTLE_MEDIA_TYPE = URIRef("https://www.iana.org/assignments/media-types/text/turtle")
DEFAULT_LICENSE = "https://creativecommons.org/licenses/by/4.0/"

SF_TYPES = {
    "Point", "MultiPoint", "LineString", "MultiLineString",
    "Polygon", "MultiPolygon", "Geometry",
}


@dataclass
class FeatureRecord:
    """One mapped feature, already stripped of any QGIS type."""
    key: str                          # stable within the layer (fid, or a uuid column)
    wkt: Optional[str] = None         # bare WKT, no CRS prefix
    sf_type: str = "Geometry"         # one of SF_TYPES
    # field concept IRI -> value concept IRIs (only non-empty fields)
    values: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class LayerRecord:
    name: str
    object_id: str
    object_label: str = ""
    object_type: str = ""             # CRM class IRI (an E18 subclass); "" -> E19
    annotation_fields: List[str] = field(default_factory=list)   # field concept IRIs
    vocab_schemes: List[str] = field(default_factory=list)       # bound ConceptScheme IRIs
    crs_iri: Optional[str] = None     # OGC URI when the layer CRS is resolvable
    raster_name: str = ""             # optional: name of the raster that defines the local CRS
    features: List[FeatureRecord] = field(default_factory=list)


@dataclass
class ExportMeta:
    """Dataset-level metadata (DCAT) and provenance of this export run."""
    title: str
    creator: str                      # IRI or plain name
    license: str = DEFAULT_LICENSE
    issued: str = ""                  # xsd:date  (YYYY-MM-DD), injected by the caller
    created: str = ""                 # xsd:dateTime, injected by the caller
    version: str = "1.0"
    local_crs: bool = False           # True: geometries live in an object-local CRS
    file_name: str = "export.ttl"
    object_namespace: str = DEFAULT_OBJECT_NAMESPACE
    data_namespace: str = DEFAULT_DATA_NAMESPACE
    description: str = ""


# ─── Small helpers ────────────────────────────────────────────────────────────

def ensure_trailing(ns: str) -> str:
    ns = ns.strip()
    return ns if ns.endswith(("/", "#")) else ns + "/"


def slug(text: str) -> str:
    """ASCII-safe, IRI-safe, deterministic fragment ('Top view' -> 'Top-view')."""
    s = re.sub(r"[^A-Za-z0-9._]+", "-", str(text).strip()).strip("-")
    return s or "x"


def field_slug(field_iri: str) -> str:
    return slug(field_iri.rstrip("/#").split("/")[-1].split("#")[-1])


def is_iri(s: str) -> bool:
    return str(s).startswith(("http://", "https://"))


def resolve_crm_class(ref: str) -> URIRef:
    """'crm:E22_Human-Made_Object', 'E22_Human-Made_Object' or a full IRI -> IRI."""
    ref = str(ref or "").strip()
    if not ref:
        return NS_CRM.E19_Physical_Object
    if is_iri(ref):
        return URIRef(ref)
    if ref.startswith("crm:"):
        return NS_CRM[ref[4:]]
    return NS_CRM[ref]


def _agent(value: str):
    return URIRef(value) if is_iri(value) else Literal(value)


def bind_prefixes(g: Graph, vocab_prefixes: Optional[Dict[str, str]],
                  object_namespace: str, data_namespace: str) -> None:
    g.bind("qskos", NS_QSKOS)
    g.bind("crm", NS_CRM)
    g.bind("geo", NS_GEO)
    g.bind("sf", NS_SF)
    g.bind("oa", NS_OA)
    g.bind("as", NS_AS)
    g.bind("dcat", NS_DCAT)
    g.bind("dct", DCTERMS)
    g.bind("skos", SKOS)
    g.bind("obj", Namespace(object_namespace))
    g.bind("qdata", Namespace(data_namespace))
    for ns_uri, prefix in sorted((vocab_prefixes or {}).items()):
        if ns_uri.endswith(("/", "#")):      # a scheme IRI like .../scheme is no namespace
            g.bind(prefix, Namespace(ns_uri), override=False)


# ─── Graph construction ───────────────────────────────────────────────────────

def build_graph(layers: List[LayerRecord], meta: ExportMeta,
                vocab_prefixes: Optional[Dict[str, str]] = None):
    """Build the export graph.

    Returns (graph, n_features, warnings).  No clock is read here: the caller
    passes meta.issued / meta.created, so the same input gives the same graph.
    """
    obj_ns = Namespace(ensure_trailing(meta.object_namespace))
    D = Namespace(ensure_trailing(meta.data_namespace))
    g = Graph()
    bind_prefixes(g, vocab_prefixes, str(obj_ns), str(D))
    warnings: List[str] = []

    active = [l for l in layers if str(l.object_id).strip()]
    if not active:
        return g, 0, ["no layer with an object ID"]

    ds = D["ds-" + slug(meta.title)]
    dist = D["dist-" + slug(meta.title)]
    catalog = D["catalog"]
    creator = _agent(meta.creator) if meta.creator else None

    # DCAT layer ---------------------------------------------------------
    g.add((catalog, RDF.type, NS_QSKOS.Catalog))
    g.add((catalog, DCTERMS.title, Literal(f"QSKOS exports: {meta.title}", lang="en")))
    g.add((catalog, NS_DCAT.dataset, ds))

    g.add((ds, RDF.type, NS_QSKOS.Dataset))
    g.add((ds, DCTERMS.title, Literal(meta.title, lang="en")))
    if meta.description:
        g.add((ds, DCTERMS.description, Literal(meta.description, lang="en")))
    if creator is not None:
        g.add((ds, DCTERMS.creator, creator))
    if meta.license:
        g.add((ds, DCTERMS.license, URIRef(meta.license)))
    if meta.issued:
        g.add((ds, DCTERMS.issued, Literal(meta.issued, datatype=XSD.date)))
    g.add((ds, NS_DCAT.version, Literal(meta.version)))
    g.add((ds, DCTERMS.conformsTo, URIRef(str(NS_QSKOS)[:-1])))
    g.add((ds, NS_DCAT.distribution, dist))

    g.add((dist, RDF.type, NS_QSKOS.Distribution))
    g.add((dist, DCTERMS.title, Literal("Turtle export", lang="en")))
    g.add((dist, NS_DCAT.mediaType, TURTLE_MEDIA_TYPE))
    g.add((dist, DCTERMS.identifier, Literal(meta.file_name)))
    g.add((dist, DCTERMS.conformsTo, URIRef(str(NS_QSKOS)[:-1])))

    n_features = 0
    seen_objects = set()
    seen_schemes = set()

    for layer in active:
        oid = str(layer.object_id).strip()
        obj = URIRef(oid) if is_iri(oid) else obj_ns[oid]
        oslug = slug(oid.rstrip("/#").split("/")[-1])
        lslug = slug(layer.name)

        # Physical object (once, even if several layers share the ID)
        if obj not in seen_objects:
            seen_objects.add(obj)
            g.add((obj, RDF.type, NS_QSKOS.MappedObject))
            g.add((obj, RDF.type, resolve_crm_class(layer.object_type)))
            if layer.object_label:
                g.add((obj, RDFS.label, Literal(layer.object_label)))
            g.add((ds, DCTERMS.subject, obj))

        # Layer
        lay = D[f"layer/{oslug}-{lslug}"]
        g.add((lay, RDF.type, NS_QSKOS.FeatureLayer))
        g.add((lay, RDFS.label, Literal(layer.name)))
        g.add((ds, DCTERMS.hasPart, lay))
        for fld in layer.annotation_fields:
            g.add((lay, NS_QSKOS.hasAttribute, URIRef(fld)))
        for scheme in layer.vocab_schemes:
            g.add((lay, NS_QSKOS.usesVocabulary, URIRef(scheme)))
            seen_schemes.add(scheme)

        # Coordinate reference system
        crs = None
        if meta.local_crs:
            crs = D[f"crs/{oslug}-{lslug}"]
            g.add((crs, RDF.type, NS_QSKOS.LocalCoordinateSystem))
            g.add((crs, RDFS.label, Literal(f"Local 2D system, {layer.name} ({oid})")))
            if layer.raster_name:
                g.add((crs, NS_QSKOS.definedByRaster, Literal(layer.raster_name)))
            crs_prefix = str(crs)
        else:
            crs_prefix = layer.crs_iri
            if not crs_prefix:
                warnings.append(
                    f"layer '{layer.name}': CRS has no OGC URI; WKT written without "
                    "CRS prefix (GeoSPARQL then assumes CRS84)")

        for feat in layer.features:
            fid = slug(feat.key)
            f_iri = D[f"feature/{oslug}-{lslug}-{fid}"]
            g.add((f_iri, RDF.type, NS_QSKOS.Feature))
            g.add((lay, RDFS.member, f_iri))
            g.add((f_iri, NS_CRM.P157_is_at_rest_relative_to, obj))
            g.add((f_iri, NS_OA.hasSource, obj))

            if feat.wkt:
                geom = D[f"geom/{oslug}-{lslug}-{fid}"]
                g.add((f_iri, NS_GEO.hasGeometry, geom))
                g.add((f_iri, NS_OA.hasSelector, geom))
                g.add((geom, RDF.type, NS_QSKOS.Geometry))
                sf = feat.sf_type if feat.sf_type in SF_TYPES else "Geometry"
                g.add((geom, RDF.type, NS_SF[sf]))
                if crs is not None:
                    g.add((geom, NS_QSKOS.inCoordinateSystem, crs))
                text = f"<{crs_prefix}> {feat.wkt}" if crs_prefix else feat.wkt
                g.add((geom, NS_GEO.asWKT, Literal(text, datatype=NS_GEO.wktLiteral)))

            for fld in sorted(feat.values):
                vals = sorted(set(feat.values[fld]))
                if not vals:
                    continue
                ann = D[f"ann/{oslug}-{lslug}-{fid}-{field_slug(fld)}"]
                g.add((ann, RDF.type, NS_QSKOS.Annotation))
                g.add((ann, NS_OA.motivatedBy, NS_OA.classifying))
                g.add((ann, NS_OA.hasTarget, f_iri))
                g.add((ann, NS_QSKOS.attribute, URIRef(fld)))
                for v in vals:
                    g.add((ann, NS_OA.hasBody, URIRef(v)))
                if creator is not None:
                    g.add((ann, DCTERMS.creator, creator))
                if meta.created:
                    g.add((ann, DCTERMS.created,
                           Literal(meta.created, datatype=XSD.dateTime)))
                g.add((ann, NS_AS.generator, GENERATOR_IRI))
            n_features += 1

    for scheme in sorted(seen_schemes):
        g.add((ds, DCTERMS.requires, URIRef(scheme)))
        g.add((URIRef(scheme), RDF.type, SKOS.ConceptScheme))

    return g, n_features, warnings


def serialize_deterministic(g: Graph, path: str) -> None:
    """Turtle with a stable statement order (sorted N-Triples -> Turtle)."""
    nt = "\n".join(sorted(g.serialize(format="nt").splitlines()))
    h = Graph()
    for prefix, ns in g.namespaces():
        h.bind(prefix, ns, override=True)
    h.parse(data=nt, format="nt")
    h.serialize(destination=path, format="turtle")
