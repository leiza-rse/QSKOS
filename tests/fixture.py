"""Synthetic export used by the tests, the example file and the statistics page.

No QGIS needed: it builds the plain records of utils/rdf_model.py directly.
The vocabulary IRIs are invented (example.org); they are not a real thesaurus.
"""
from utils.rdf_model import ExportMeta, FeatureRecord, LayerRecord

EXV = "https://example.org/vocab/"
SCHEME = EXV + "scheme"
LAYER_NAME = "Top view - polygons"
OBJECT_ID = "O.34736"
FIXED_ISSUED = "2026-10-28"
FIXED_CREATED = "2026-10-28T09:00:00Z"
LOCAL_CRS_WKT_1 = "POLYGON ((30 10, 40 40, 20 40, 10 20, 30 10))"
LOCAL_CRS_WKT_2 = "POLYGON ((50 10, 60 10, 60 20, 50 20, 50 10))"


def make_layer(unannotated=True):
    feats = [
        FeatureRecord(
            key="1", wkt=LOCAL_CRS_WKT_1, sf_type="Polygon",
            values={EXV + "Material": [EXV + "Leather"],
                    EXV + "Damage": [EXV + "Crack", EXV + "Abrasion"]}),
        FeatureRecord(
            key="2", wkt=LOCAL_CRS_WKT_2, sf_type="Polygon",
            values={EXV + "Material": [EXV + "Textile"]}),
    ]
    if unannotated:
        feats.append(FeatureRecord(
            key="3", wkt="POLYGON ((0 0, 5 0, 5 5, 0 5, 0 0))", sf_type="Polygon"))
    return LayerRecord(
        name=LAYER_NAME, object_id=OBJECT_ID, object_label="Lederschuh",
        object_type="http://www.cidoc-crm.org/cidoc-crm/E22_Human-Made_Object",
        annotation_fields=[EXV + "Material", EXV + "Damage", EXV + "Intervention"],
        vocab_schemes=[SCHEME],
        crs_iri="http://www.opengis.net/def/crs/EPSG/0/4326",
        raster_name="O.34736_top_ortho.tif", features=feats)


def make_meta(local_crs=True):
    return ExportMeta(
        title="Condition mapping of Roman leather shoe O.34736",
        creator="https://example.org/person/conservator-1",
        license="https://creativecommons.org/licenses/by-sa/4.0/",
        issued=FIXED_ISSUED, created=FIXED_CREATED, version="0.1",
        local_crs=local_crs, file_name="example.ttl",
        description="Annotated features on the top-view orthomosaic, "
                    "classified with a SKOS vocabulary.")


VOCAB_PREFIXES = {EXV: "exv"}
