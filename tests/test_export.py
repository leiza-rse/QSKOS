"""Tests for the QSKOS RDF export.  Run from the repository root:

    python -m unittest discover -s tests -v        (or:  python tools/main.py --only test)

No QGIS needed.  pyshacl is optional for the model tests; the SHACL tests are
skipped without it (set QSKOS_STRICT=1 to make that an error).
"""
import os
import re
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import ontology_io as oio                                  # noqa: E402
from tools.ontology_io import (Graph, RDF, RDFS, URIRef, QSKOS,        # noqa: E402
                               ONTOLOGY, SHAPES, QUERIES)
from rdflib import Literal                                            # noqa: E402
from rdflib.namespace import DCTERMS                                  # noqa: E402
from tests import fixture as fx                                        # noqa: E402
from utils.rdf_model import (build_graph, serialize_deterministic,   # noqa: E402
                             slug, resolve_crm_class, NS_GEO)

try:
    from pyshacl import validate as shacl_validate
except ImportError:                                                   # pragma: no cover
    shacl_validate = None

PFX = """PREFIX qskos: <http://archaeology.link/ontology/qskos#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
PREFIX oa: <http://www.w3.org/ns/oa#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX exv: <https://example.org/vocab/>
PREFIX crm: <http://www.cidoc-crm.org/cidoc-crm/>
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX dcat: <http://www.w3.org/ns/dcat#>
"""


def queries():
    raw = QUERIES.read_text(encoding="utf-8")
    parts = re.split(r"^# ===== (Q\d)[^\n]*\n", raw, flags=re.M)
    out = {}
    for i in range(1, len(parts), 2):
        body = "\n".join(l for l in parts[i + 1].splitlines()
                         if not l.startswith("#") and not l.startswith("PREFIX"))
        out[parts[i]] = PFX + body
    return out


def export_graph(local_crs=True, unannotated=True):
    g, n, w = build_graph([fx.make_layer(unannotated)], fx.make_meta(local_crs), fx.VOCAB_PREFIXES)
    return g, n, w


def full_store():
    g, _, _ = export_graph()
    g.parse(oio.EXAMPLE_VOCAB)
    return g


class ModelTests(unittest.TestCase):
    def test_counts(self):
        g, n, w = export_graph()
        self.assertEqual(n, 3)
        self.assertEqual(w, [])
        for cls, expected in [("Feature", 3), ("Geometry", 3), ("Annotation", 3),
                              ("Dataset", 1), ("Catalog", 1), ("Distribution", 1),
                              ("FeatureLayer", 1), ("LocalCoordinateSystem", 1),
                              ("MappedObject", 1)]:
            self.assertEqual(len(list(g.subjects(RDF.type, QSKOS[cls]))), expected, cls)

    def test_data_uses_only_qskos_classes(self):
        g, _, _ = export_graph()
        allowed = ("http://archaeology.link/ontology/qskos#", "http://www.opengis.net/ont/sf#",
                   "http://www.cidoc-crm.org/cidoc-crm/E22", "http://www.w3.org/2004/02/skos/core#ConceptScheme")
        bad = [(s, o) for s, o in g.subject_objects(RDF.type) if not str(o).startswith(allowed)]
        self.assertEqual(bad, [])

    def test_multi_value_cell_is_one_annotation(self):
        g, _, _ = export_graph()
        ann = [a for a in g.subjects(QSKOS.attribute, URIRef(fx.EXV + "Damage"))]
        self.assertEqual(len(ann), 1)
        self.assertEqual(len(list(g.objects(ann[0], URIRef("http://www.w3.org/ns/oa#hasBody")))), 2)

    def test_unannotated_feature_is_exported(self):
        g, _, _ = export_graph(unannotated=True)
        members = set(g.objects(None, RDFS.member))
        annotated = set(g.objects(None, URIRef("http://www.w3.org/ns/oa#hasTarget")))
        self.assertEqual(len(members - annotated), 1)

    def test_deterministic_ids_and_graph(self):
        a, _, _ = export_graph()
        b, _, _ = export_graph()
        self.assertEqual(sorted(a.serialize(format="nt").splitlines()),
                         sorted(b.serialize(format="nt").splitlines()))

    def test_serialisation_is_byte_stable(self):
        import tempfile
        g, _, _ = export_graph()
        with tempfile.TemporaryDirectory() as d:
            p1, p2 = Path(d, "a.ttl"), Path(d, "b.ttl")
            serialize_deterministic(g, str(p1))
            serialize_deterministic(g, str(p2))
            self.assertEqual(p1.read_bytes(), p2.read_bytes())

    def test_unicorn_crs_split(self):
        # Re-implementation of SPARQLing Unicorn's literal handling
        # (util/layerutils.py): '<...>' prefix -> CRS name = last IRI segment.
        g, _, _ = export_graph()
        lits = [str(o) for o in g.objects(None, NS_GEO.asWKT)]
        self.assertEqual(len(lits), 3)
        for lit in lits:
            self.assertTrue(lit.startswith("<http"))
            idx = lit.index(">") + 1
            crs = lit[lit.rfind("/", 0, idx) + 1:idx - 1]
            self.assertEqual(crs, "O.34736-Top-view-polygons")
            self.assertTrue(lit[idx:].strip().startswith("POLYGON"))

    def test_geographic_mode_uses_epsg_and_no_local_crs(self):
        g, _, w = export_graph(local_crs=False)
        self.assertEqual(w, [])
        self.assertEqual(len(list(g.subjects(RDF.type, QSKOS.LocalCoordinateSystem))), 0)
        for o in g.objects(None, NS_GEO.asWKT):
            self.assertTrue(str(o).startswith("<http://www.opengis.net/def/crs/EPSG/0/4326> "))

    def test_missing_crs_warns(self):
        layer = fx.make_layer()
        layer.crs_iri = None
        g, _, w = build_graph([layer], fx.make_meta(local_crs=False), fx.VOCAB_PREFIXES)
        self.assertEqual(len(w), 1)

    def test_layers_sharing_an_object_id_share_the_object(self):
        l1, l2 = fx.make_layer(), fx.make_layer()
        l2.name = "Side view"
        g, _, _ = build_graph([l1, l2], fx.make_meta(), fx.VOCAB_PREFIXES)
        self.assertEqual(len(list(g.subjects(RDF.type, QSKOS.MappedObject))), 1)
        self.assertEqual(len(list(g.subjects(RDF.type, QSKOS.FeatureLayer))), 2)

    def test_helpers(self):
        self.assertEqual(slug("Top view - polygons"), "Top-view-polygons")
        self.assertEqual(str(resolve_crm_class("crm:E22_Human-Made_Object")),
                         "http://www.cidoc-crm.org/cidoc-crm/E22_Human-Made_Object")
        self.assertEqual(str(resolve_crm_class("")), "http://www.cidoc-crm.org/cidoc-crm/E19_Physical_Object")

    def test_example_file_is_current(self):
        """ontology/example.ttl must equal what the builder writes now."""
        import tempfile
        g, _, _ = export_graph()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "example.ttl")
            serialize_deterministic(g, str(p))
            self.assertEqual(p.read_bytes(), oio.EXAMPLE.read_bytes(),
                             "run: python tools/main.py --only example")


class QueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = full_store()
        cls.q = queries()
        cls.layer = [str(s) for s in cls.store.subjects(RDF.type, QSKOS.FeatureLayer)][0]
        cls.q["Q1"] = cls.q["Q1"].replace("<LAYER>", f"<{cls.layer}>")

    def test_q1_unicorn_contract(self):
        rows = list(self.store.query(self.q["Q1"]))
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r.item is not None and r.geo is not None for r in rows))
        mats = sorted(str(r.material) for r in rows if str(r.material))
        self.assertEqual(mats, ["leather", "textile"])

    def test_q2_descendants(self):
        items = {str(r.item) for r in self.store.query(self.q["Q2"])}
        self.assertEqual(len(items), 1)

    def test_q3_crm_shortcuts(self):
        self.assertEqual(len(self.store.query(self.q["Q3"]).graph), 3 + 4)    # 3 x P140 + 4 x P141

    def test_q4_flat_projection(self):
        self.assertEqual(len(self.store.query(self.q["Q4"]).graph), 4)

    def test_q5_provenance(self):
        g = self.store.query(self.q["Q5"]).graph
        P14 = URIRef("http://www.cidoc-crm.org/cidoc-crm/P14_carried_out_by")
        P4 = URIRef("http://www.cidoc-crm.org/cidoc-crm/P4_has_time-span")
        self.assertEqual(len(list(g.subject_objects(P14))), 3)
        self.assertEqual(len(list(g.subject_objects(P4))), 3)

    def test_q6_dcat_view(self):
        rows = list(self.store.query(self.q["Q6"]))
        self.assertEqual(len(rows), 1)
        self.assertEqual(int(rows[0].features), 3)

    def test_q7_no_wkt_without_crs(self):
        self.assertEqual(len(list(self.store.query(self.q["Q7"]))), 0)


class OntologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.onto = oio.ontology()
        cls.full = oio.with_parent_stub(cls.onto)

    def test_every_qskos_class_reaches_its_root(self):
        E1 = URIRef(oio.CRM + "E1_CRM_Entity")
        for c in oio.qskos_classes(self.onto):
            self.assertIn(E1, set(self.full.transitive_objects(c, RDFS.subClassOf)), c)

    def test_every_class_has_a_dcat_or_crm_superclass_and_documentation(self):
        for c in oio.qskos_classes(self.onto):
            sup = oio.direct_superclasses(self.onto, c)
            self.assertTrue(sup, c)
            self.assertTrue(oio.comment(self.onto, c), f"no rdfs:comment on {c}")

    def test_feature_is_not_sp6_and_not_e26(self):
        sup = {str(s) for s in oio.direct_superclasses(self.onto, QSKOS.Feature)}
        self.assertNotIn(oio.CRMGEO + "SP6_Declarative_Place", sup)
        self.assertNotIn(oio.CRM + "E26_Physical_Feature", sup)
        self.assertIn(oio.CRM + "E53_Place", sup)

    def test_ontology_asserts_only_for_own_terms(self):
        for s, _, _ in self.onto.triples((None, RDFS.subClassOf, None)):
            self.assertTrue(str(s).startswith(str(QSKOS)), s)
        for s, _, _ in self.onto.triples((None, RDFS.subPropertyOf, None)):
            self.assertTrue(str(s).startswith(str(QSKOS)), s)

    def test_crmgeo_namespace(self):
        text = ONTOLOGY.read_text(encoding="utf-8")
        self.assertIn("http://www.ics.forth.gr/isl/CRMgeo/", text)
        self.assertNotIn("CRMgeo#", text)


@unittest.skipIf(shacl_validate is None and not os.environ.get("QSKOS_STRICT"), "pyshacl not installed")
class ShaclTests(unittest.TestCase):
    def setUp(self):
        if shacl_validate is None:
            self.fail("pyshacl missing (QSKOS_STRICT set)")
        self.shapes = Graph().parse(SHAPES)

    def test_local_crs_export_conforms(self):
        g, _, _ = export_graph(local_crs=True)
        ok, _, text = shacl_validate(g, shacl_graph=self.shapes, inference="none")
        self.assertTrue(ok, text[:800])

    def test_geographic_export_conforms(self):
        g, _, _ = export_graph(local_crs=False)
        ok, _, text = shacl_validate(g, shacl_graph=self.shapes, inference="none")
        self.assertTrue(ok, text[:800])

    def test_rejects_wkt_without_crs_prefix(self):
        g, _, _ = export_graph()
        geom = next(g.subjects(RDF.type, QSKOS.Geometry))
        g.remove((geom, NS_GEO.asWKT, None))
        g.add((geom, NS_GEO.asWKT, Literal("POLYGON ((0 0, 1 1, 1 0, 0 0))", datatype=NS_GEO.wktLiteral)))
        ok, _, _ = shacl_validate(g, shacl_graph=self.shapes, inference="none")
        self.assertFalse(ok)

    def test_rejects_dataset_without_licence(self):
        g, _, _ = export_graph()
        ds = next(g.subjects(RDF.type, QSKOS.Dataset))
        g.remove((ds, DCTERMS.license, None))
        ok, _, _ = shacl_validate(g, shacl_graph=self.shapes, inference="none")
        self.assertFalse(ok)


class AdapterTests(unittest.TestCase):
    """utils/lod.py with a stub of qgis.core and fake layers (no QGIS needed)."""

    @classmethod
    def setUpClass(cls):
        qgis = types.ModuleType("qgis")
        core = types.ModuleType("qgis.core")

        class Wkb:
            PolygonGeometry, PointGeometry, LineGeometry = 2, 0, 1
        core.QgsWkbTypes = Wkb
        qgis.core = core
        sys.modules.setdefault("qgis", qgis)
        sys.modules["qgis.core"] = core
        if "PyQt5" not in sys.modules:             # fields.py only needs QVariant
            pyqt, qtcore = types.ModuleType("PyQt5"), types.ModuleType("PyQt5.QtCore")
            qtcore.QVariant = type("QVariant", (), {})
            pyqt.QtCore = qtcore
            sys.modules["PyQt5"], sys.modules["PyQt5.QtCore"] = pyqt, qtcore
        # utils is a package inside the plugin; import it as such
        import importlib
        cls.lod = importlib.import_module("utils.lod")
        cls.Wkb = Wkb

    def _layer(self):
        Wkb = self.Wkb

        class Geom:
            def __init__(s, wkt, kind, multi=False): s.w, s.k, s.m = wkt, kind, multi
            def isNull(s): return False
            def isEmpty(s): return False
            def isMultipart(s): return s.m
            def type(s): return s.k
            def asWkt(s): return s.w

        class Feat:
            def __init__(s, fid, geom, vals): s._id, s._g, s._v = fid, geom, vals
            def id(s): return s._id
            def geometry(s): return s._g
            def __getitem__(s, i): return s._v[i]

        class Fields:
            names = [fx.EXV + "Material", fx.EXV + "Damage"]   # field names ARE concept IRIs
            def lookupField(s, n): return s.names.index(n) if n in s.names else -1

        class Crs:
            def authid(s): return "EPSG:4326"

        class Layer:
            def name(s): return fx.LAYER_NAME
            def fields(s): return Fields()
            def crs(s): return Crs()
            def getFeatures(s):
                return [Feat(7, Geom(fx.LOCAL_CRS_WKT_1, Wkb.PolygonGeometry),
                             [f'["{fx.EXV}Leather"]', f'["{fx.EXV}Crack"|"{fx.EXV}Abrasion"]'.replace('"|"', '", "')]),
                        Feat(8, Geom("POINT (1 2)", Wkb.PointGeometry), [None, ""])]
        return Layer()

    def test_adapter_builds_same_model(self):
        from utils.rdf_model import ExportMeta
        spec = {"layer": self._layer(), "annotation_fields": [fx.EXV + "Material", fx.EXV + "Damage"],
                "object_id": "O.1", "object_label": "x", "object_type": "crm:E22_Human-Made_Object",
                "vocab_schemes": [fx.SCHEME]}
        meta = ExportMeta(title="T", creator="Me", local_crs=False)
        g, n, w = self.lod.build_lod_graph([spec], None, fx.VOCAB_PREFIXES, meta)
        self.assertEqual(n, 2)
        self.assertEqual(len(list(g.subjects(RDF.type, QSKOS.Annotation))), 2)   # Material + Damage of feature 7
        self.assertEqual(len(list(g.subjects(RDF.type, QSKOS.Feature))), 2)
        sf = {str(o) for o in g.objects(None, RDF.type) if "opengis.net/ont/sf" in str(o)}
        self.assertEqual(sf, {"http://www.opengis.net/ont/sf#Polygon", "http://www.opengis.net/ont/sf#Point"})
        # export clock is read only by the adapter
        self.assertTrue(any(True for _ in g.objects(None, DCTERMS.issued)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
