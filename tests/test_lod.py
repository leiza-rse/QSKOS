# test_lod.py
# qskos QGIS Plugin - unit tests for utils/lod.py (pure LOD graph builder).
# No QGIS runtime required; specs are the extracted data structure.

from rdflib import Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS

from qskos.utils.lod import (
    build_lod_graph,
    export_lod_ttl,
    derive_prefix,
    ogc_crs_uri,
    sf_class_from_names,
    NS_CRM,
    NS_CRMDIG,
    NS_OA,
    NS_GEOSPARQL,
    NS_SF,
    DEFAULT_OBJECT_NAMESPACE,
)


def _spec(object_id="O.1", features=None, label="L", obj_type="crm:E22_Human_Made_Object"):
    return {
        "object_id": object_id,
        "object_label": label,
        "object_type": obj_type,
        "features": features or [
            {"values": {"http://field": ["http://concept"]},
             "wkt": None, "crs_uri": None, "sf_class": None},
        ],
    }


class TestHelpers:
    def test_ogc_crs_uri(self):
        assert ogc_crs_uri("EPSG:4326") == \
            "http://www.opengis.net/def/crs/EPSG/0/4326"
        assert ogc_crs_uri("") is None
        assert ogc_crs_uri("EPSG:bad") is None

    def test_sf_class_from_names(self):
        assert sf_class_from_names("Polygon", False) == "Polygon"
        assert sf_class_from_names("Polygon", True) == "MultiPolygon"
        assert sf_class_from_names("Point", False) == "Point"
        assert sf_class_from_names("Point", True) == "MultiPoint"
        assert sf_class_from_names("Line", False) == "LineString"
        assert sf_class_from_names("Line", True) == "MultiLineString"
        assert sf_class_from_names("Unknown", False) == "Geometry"

    def test_derive_prefix(self):
        assert derive_prefix("http://example.org/MyVocab") == "MyVocab"
        assert derive_prefix("http://x/y-z") == "y_z"


class TestBuildGraph:
    def test_object_typing_and_label(self):
        g, n = build_lod_graph([_spec()])
        obj = URIRef(DEFAULT_OBJECT_NAMESPACE + "O.1")
        assert (obj, RDF.type, NS_CRM.E22_Human_Made_Object) in g
        assert (obj, RDFS.label, Literal("L")) in g
        assert n == 1

    def test_annotation_node_mapping(self):
        g, n = build_lod_graph([_spec()])
        obj = URIRef(DEFAULT_OBJECT_NAMESPACE + "O.1")
        anns = set(g.objects(obj, NS_CRM.P56_bears_feature))
        assert len(anns) == 1
        ann = anns.pop()
        assert (ann, RDF.type, NS_CRMDIG.D9_Data_Object) in g
        assert (ann, RDF.type, NS_OA.Annotation) in g
        assert (ann, NS_OA.hasBody, obj) in g
        assert (ann, NS_OA.motivatedBy, URIRef("http://field")) in g
        assert (ann, NS_OA.hasTarget, URIRef("http://concept")) in g

    def test_geometry_added(self):
        spec = _spec(features=[
            {"values": {"http://f": ["http://c"]},
             "wkt": "POLYGON ((0 0, 1 0, 1 1, 0 0))",
             "crs_uri": "http://www.opengis.net/def/crs/EPSG/0/4326",
             "sf_class": "Polygon"},
        ])
        g, n = build_lod_graph([spec])
        obj = URIRef(DEFAULT_OBJECT_NAMESPACE + "O.1")
        ann = next(iter(g.objects(obj, NS_CRM.P56_bears_feature)))
        geom = next(iter(g.objects(ann, NS_GEOSPARQL.hasGeometry)))
        assert (geom, RDF.type, NS_SF.Polygon) in g
        wkt = g.value(geom, NS_GEOSPARQL.asWKT)
        assert "POLYGON" in str(wkt)

    def test_skip_when_no_object_id(self):
        g, n = build_lod_graph([_spec(object_id="  ")])
        assert n == 0

    def test_merge_same_object_id(self):
        g, n = build_lod_graph([
            _spec(object_id="O.1", features=[
                {"values": {"http://f1": ["http://c1"]},
                 "wkt": None, "crs_uri": None, "sf_class": None}]),
            _spec(object_id="O.1", features=[
                {"values": {"http://f2": ["http://c2"]},
                 "wkt": None, "crs_uri": None, "sf_class": None}]),
        ])
        obj = URIRef(DEFAULT_OBJECT_NAMESPACE + "O.1")
        assert len(set(g.objects(obj, NS_CRM.P56_bears_feature))) == 2
        assert n == 2

    def test_default_object_class(self):
        g, n = build_lod_graph([_spec(obj_type="")])
        obj = URIRef(DEFAULT_OBJECT_NAMESPACE + "O.1")
        assert (obj, RDF.type, NS_CRM.E19_Physical_Object) in g


class TestExport:
    def test_export_writes_ttl(self, tmp_path):
        out = str(tmp_path / "out.ttl")
        n = export_lod_ttl(out, [_spec()])
        assert n == 1
        with open(out, encoding="utf-8") as f:
            content = f.read()
        assert "P56_bears_feature" in content
