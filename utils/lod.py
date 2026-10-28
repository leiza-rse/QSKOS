# lod.py
# qskos QGIS Plugin - Linked Open Data Export Utilities
# QGIS adapter for the RDF export: reads layers/features and hands plain
# records to utils/rdf_model.py, which builds the graph.  Pure data logic —
# no tab logic lives here.
#
# Data model (see ontology/qskos.ttl and docs/):
#   qskos:Catalog -dcat:dataset-> qskos:Dataset -dcat:distribution-> qskos:Distribution
#   qskos:Dataset -dct:hasPart-> qskos:FeatureLayer -rdfs:member-> qskos:Feature
#   qskos:Feature -geo:hasGeometry-> qskos:Geometry (geo:asWKT "<CRS-IRI> WKT")
#   qskos:Annotation -oa:hasTarget-> Feature ; -qskos:attribute-> field concept ;
#                    -oa:hasBody-> value concept(s)
# The crosswalk to DCAT / GeoSPARQL / Web Annotation / CIDOC CRM lives only in
# the ontology (rdfs:subClassOf); the data carries qskos: classes.

import re
from datetime import datetime, timezone

from qgis.core import QgsWkbTypes

from .fields import parse_field_value
from .rdf_model import (
    DEFAULT_DATA_NAMESPACE, DEFAULT_LICENSE, DEFAULT_OBJECT_NAMESPACE,
    ExportMeta, FeatureRecord, LayerRecord, build_graph, ensure_trailing,
    resolve_crm_class, serialize_deterministic,
)

# Kept for backward compatibility with callers of the old module.
DEFAULT_ANNOTATION_NAMESPACE = DEFAULT_DATA_NAMESPACE

# NB: CIDOC CRM 7.1 spells these with a hyphen (E22_Human-Made_Object).
OBJECT_CLASS = resolve_crm_class("")


# ─── Helpers ──────────────────────────────────────────────────────────────────

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


def _sf_name(geom):
    """Map a QgsGeometry to the local name of the matching sf: class."""
    is_multi = geom.isMultipart()
    geom_type = geom.type()
    if geom_type == QgsWkbTypes.PolygonGeometry:
        return "MultiPolygon" if is_multi else "Polygon"
    if geom_type == QgsWkbTypes.PointGeometry:
        return "MultiPoint" if is_multi else "Point"
    if geom_type == QgsWkbTypes.LineGeometry:
        return "MultiLineString" if is_multi else "LineString"
    return "Geometry"


def derive_prefix(scheme_uri):
    """Derive a Turtle prefix from the last path segment of a scheme URI."""
    name = scheme_uri.rstrip("/#").split("/")[-1]
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    return name or "vocab"


def now_stamps():
    """(date, dateTime) of the export, UTC — the only clock read in the export."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%dT%H:%M:%SZ")


def _layer_record(spec, vocab_prefixes):
    layer = spec["layer"]
    fields = layer.fields()
    crs = layer.crs()
    # An optional stable key column wins over the QGIS feature id (fid is only
    # stable as long as the GeoPackage rows are not re-created).
    key_idx = fields.lookupField("uuid")

    records = []
    for feat in layer.getFeatures():
        values = {}
        for field_name in spec["annotation_fields"]:
            fidx = fields.lookupField(field_name)
            if fidx == -1:
                continue
            vals = parse_field_value(feat[fidx])
            if vals:
                values[field_name] = vals
        geom = feat.geometry()
        wkt, sf = None, "Geometry"
        if geom and not geom.isNull() and not geom.isEmpty():
            wkt, sf = str(geom.asWkt()), _sf_name(geom)
        key = str(feat[key_idx]) if key_idx != -1 and feat[key_idx] else str(feat.id())
        records.append(FeatureRecord(key=key, wkt=wkt, sf_type=sf, values=values))

    return LayerRecord(
        name=layer.name(),
        object_id=str(spec.get("object_id") or "").strip(),
        object_label=spec.get("object_label") or "",
        object_type=spec.get("object_type") or "",
        annotation_fields=list(spec["annotation_fields"]),
        vocab_schemes=list(spec.get("vocab_schemes") or vocab_prefixes or []),
        crs_iri=_ogc_crs_uri(crs),
        raster_name=spec.get("raster_name") or "",
        features=records,
    )


# ─── Graph construction ───────────────────────────────────────────────────────

def build_lod_graph(layer_specs, object_namespace=None, vocab_prefixes=None,
                    meta=None):
    """
    Build the LOD graph for annotations found across several feature layers.

    Each spec in layer_specs describes one object and its annotation fields:
        {
            "layer":             QgsVectorLayer,
            "annotation_fields": [field names that are concept URIs, …],
            "object_id":         str (appended to object_namespace),
            "object_label":      str,
            "object_type":       str (CRM class ref, default crm:E19_Physical_Object),
            "vocab_schemes":     [ConceptScheme IRIs bound to the layer]  (optional)
        }

    meta — ExportMeta (title, creator, licence, local_crs …).  If omitted a
    minimal one is derived, so old callers keep working.

    Layers sharing the same object_id produce the same object IRI.

    Returns (graph, n_features_exported, warnings).
    """
    if meta is None:
        meta = ExportMeta(title="QSKOS export", creator="")
    d, dt = now_stamps()
    meta.issued = meta.issued or d
    meta.created = meta.created or dt
    meta.object_namespace = ensure_trailing(
        object_namespace or meta.object_namespace or DEFAULT_OBJECT_NAMESPACE)
    records = [_layer_record(s, vocab_prefixes) for s in layer_specs]
    return build_graph(records, meta, vocab_prefixes)


def export_lod_ttl(output_path, layer_specs, object_namespace=None,
                   vocab_prefixes=None, meta=None):
    """
    Build the LOD graph and serialise it as Turtle to output_path.

    Returns the number of features exported.
    """
    import os
    if meta is not None:
        meta.file_name = os.path.basename(output_path)
    graph, n_features, warnings = build_lod_graph(
        layer_specs, object_namespace, vocab_prefixes, meta
    )
    for w in warnings:
        print(f"[qskos] LOD export: {w}")
    serialize_deterministic(graph, output_path)
    return n_features
