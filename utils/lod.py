# lod.py
# qskos QGIS Plugin - Linked Open Data Export Utilities
# Builds an rdflib Graph from annotated features and serialises it as Turtle.
# Pure data logic — no tab logic lives here.
#
# Data model (per feature):
#   <obj> rdf:type crm:E19_Physical_Object
#   <obj> rdfs:label "<object label>"
#   <obj> crm:P56_bears_feature <feat_N>          (one per annotation field)
#   <feat_N> rdf:type crmdig:D9_Data_Object, oa:Annotation
#   <feat_N> oa:hasBody <obj>
#   <feat_N> oa:hasTarget <concept>               (one per selected value)
#   <feat_N> oa:motivatedBy <field concept>
#   <field concept> rdf:type oa:Motivation
#   <feat_N> geosparql:hasGeometry <feat_N_geom>
#   <feat_N_geom> rdf:type sf:... ; geosparql:asWKT "<crs> <wkt>"^^geosparql:wktLiteral

import re

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS

from qgis.core import QgsWkbTypes

from .fields import parse_field_value

# ─── Namespace constants (match context/example.ttl) ─────────────────────────

NS_CRM       = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
NS_CRMDIG    = Namespace("http://www.ics.forth.gr/isl/CRMdig/")
NS_OA        = Namespace("http://www.w3.org/ns/oa#")
NS_GEOSPARQL = Namespace("http://www.opengis.net/ont/geosparql#")
NS_SF        = Namespace("http://www.opengis.net/ont/sf#")

OBJECT_CLASS = NS_CRM.E19_Physical_Object

DEFAULT_OBJECT_NAMESPACE = "http://w3id.org/archlink/objects/"
DEFAULT_ANNOTATION_NAMESPACE = "http://data.archaeology.link/data/qskos/"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _ensure_trailing(s):
    """Ensure a namespace string ends with '/' or '#' for clean URIs."""
    s = s.strip()
    if not s.endswith(("/", "#")):
        s += "/"
    return s


def _ogc_crs_uri(crs):
    """Return the OGC CRS URI for an EPSG-based CRS, else None.

    e.g. 'EPSG:4326' → 'http://www.opengis.net/def/crs/EPSG/0/4326'
    """
    authid = crs.authid() if crs else ""
    if authid.startswith("EPSG:"):
        try:
            code = int(authid.split(":", 1)[1])
            return f"http://www.opengis.net/def/crs/EPSG/0/{code}"
        except ValueError:
            return None
    return None


def _sf_class(geom):
    """Map a QgsGeometry to the matching sf: geometry class."""
    is_multi = geom.isMultipart()
    geom_type = geom.type()
    if geom_type == QgsWkbTypes.PolygonGeometry:
        return NS_SF.MultiPolygon if is_multi else NS_SF.Polygon
    if geom_type == QgsWkbTypes.PointGeometry:
        return NS_SF.MultiPoint if is_multi else NS_SF.Point
    if geom_type == QgsWkbTypes.LineGeometry:
        return NS_SF.MultiLineString if is_multi else NS_SF.LineString
    return NS_SF.Geometry


def _wkt_literal(geom, crs):
    """Return a GeoSPARQL WKT literal, embedding the CRS URI when resolvable.

    e.g. '<http://www.opengis.net/def/crs/EPSG/0/4326> POLYGON ((...))'
         ^^geosparql:wktLiteral
    """
    wkt = str(geom.asWkt())
    crs_uri = _ogc_crs_uri(crs)
    text = f"<{crs_uri}> {wkt}" if crs_uri else wkt
    return Literal(text, datatype=NS_GEOSPARQL.wktLiteral)


def derive_prefix(scheme_uri):
    """Derive a Turtle prefix from the last path segment of a scheme URI."""
    name = scheme_uri.rstrip("/#").split("/")[-1]
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    return name or "vocab"


def _is_uri(s):
    return s.startswith("http://") or s.startswith("https://")


# ─── Graph construction ───────────────────────────────────────────────────────

def _resolve_class(class_ref):
    """Resolve a user-provided CRM class reference to a URIRef.

    Accepts: a full URI, a curie like 'crm:E22_Human_Made_Object', or a bare
    class name like 'E22_Human_Made_Object' (defaults to the crm: namespace).
    """
    ref = str(class_ref).strip()
    if not ref:
        return OBJECT_CLASS
    if ref.startswith("http://") or ref.startswith("https://"):
        return URIRef(ref)
    if ":" in ref:
        prefix, local = ref.split(":", 1)
        if prefix == "crm":
            return NS_CRM[local]
        # Unknown prefix — leave as a full URI fragment fallback
        return URIRef(ref)
    return NS_CRM[ref]


def build_lod_graph(layer_specs, object_namespace=None, vocab_prefixes=None):
    """
    Build the LOD graph for annotations found across several feature layers.

    object_namespace — the institution's object namespace, applied to every
        layer's Object ID. Defaults to DEFAULT_OBJECT_NAMESPACE. The
        annotation (feature) namespace is always the plugin default.

    Each spec in layer_specs describes one object and its annotation fields:
        {
            "layer":             QgsVectorLayer,
            "annotation_fields": [field names that are concept URIs, …],
            "object_id":         str (appended to object_namespace),
            "object_label":      str,
            "object_type":       str (CRM class ref, default crm:E19_Physical_Object),
        }

    Field values (lists of concept URIs) become oa:hasTarget; the field name
    (parent concept) becomes oa:motivatedBy.

    Layers sharing the same object_id produce the same subject URI, so
    RDFlib merges (deduplicates) their triples automatically.

    Returns (graph, n_features_exported).
    """
    g = Graph()
    obj_ns = Namespace(
        _ensure_trailing(object_namespace or DEFAULT_OBJECT_NAMESPACE)
    )
    ann_ns = Namespace(_ensure_trailing(DEFAULT_ANNOTATION_NAMESPACE))

    g.bind("crm", NS_CRM)
    g.bind("crmdig", NS_CRMDIG)
    g.bind("oa", NS_OA)
    g.bind("geosparql", NS_GEOSPARQL)
    g.bind("sf", NS_SF)
    g.bind("obj", obj_ns)
    g.bind("qskos", ann_ns)
    for ns_uri, prefix in (vocab_prefixes or {}).items():
        g.bind(prefix, Namespace(ns_uri))

    counter = 0       # annotation node counter (feat_1, feat_2, …)
    n_features = 0    # features actually exported

    for spec in layer_specs:
        object_id = str(spec.get("object_id") or "").strip()
        if not object_id:
            continue  # skip layers with no object ID

        layer = spec["layer"]
        annotation_fields = spec["annotation_fields"]

        obj_uri = URIRef(object_id) if _is_uri(object_id) else obj_ns[object_id]
        g.add((obj_uri, RDF.type, _resolve_class(spec.get("object_type"))))
        if spec.get("object_label"):
            g.add((obj_uri, RDFS.label, Literal(spec["object_label"])))

        fields = layer.fields()
        crs = layer.crs()

        for feat in layer.getFeatures():
            # Collect non-empty annotation values for this feature
            values_by_field = {}
            for field_name in annotation_fields:
                fidx = fields.lookupField(field_name)
                if fidx == -1:
                    continue
                values = parse_field_value(feat[fidx])
                if values:
                    values_by_field[field_name] = values
            if not values_by_field:
                continue

            # One annotation node per annotation field
            for field_name, values in values_by_field.items():
                counter += 1
                ann_uri = ann_ns[f"feat_{counter}"]
                geom_uri = ann_ns[f"feat_{counter}_geom"]

                g.add((obj_uri, NS_CRM.P56_bears_feature, ann_uri))
                g.add((ann_uri, RDF.type, NS_CRMDIG.D9_Data_Object))
                g.add((ann_uri, RDF.type, NS_OA.Annotation))
                g.add((ann_uri, NS_OA.hasBody, obj_uri))

                # Attribute description: field concept (parent) is the motivation
                field_uri = URIRef(field_name)
                g.add((ann_uri, NS_OA.motivatedBy, field_uri))
                g.add((field_uri, RDF.type, NS_OA.Motivation))

                # Attribute values: selected concepts are the targets
                for value in values:
                    g.add((ann_uri, NS_OA.hasTarget, URIRef(value)))

                # Geometry per annotation node
                geom = feat.geometry()
                if geom and not geom.isNull() and not geom.isEmpty():
                    g.add((ann_uri, NS_GEOSPARQL.hasGeometry, geom_uri))
                    g.add((geom_uri, RDF.type, _sf_class(geom)))
                    g.add((geom_uri, NS_GEOSPARQL.asWKT, _wkt_literal(geom, crs)))

            n_features += 1

    return g, n_features


def export_lod_ttl(output_path, layer_specs, object_namespace=None,
                   vocab_prefixes=None):
    """
    Build the LOD graph and serialise it as Turtle to output_path.

    Returns the number of features exported.
    """
    graph, n_features = build_lod_graph(
        layer_specs, object_namespace, vocab_prefixes
    )
    graph.serialize(destination=output_path, format="turtle")
    return n_features
