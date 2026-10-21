# layers.py
# qskos QGIS Plugin - QGIS layer adapter
# Thin adapters over QGIS vector layers (path/table extraction, loading a
# hidden vocab layer into the project, and extracting feature/geometry data
# for LOD export). These need QGIS, so they live apart from the pure
# data-access layer (utils/gpkg.py) and pure graph builder (utils/lod.py),
# which have no QGIS imports and are unit-tested without a QGIS runtime.

from qgis.core import QgsVectorLayer, QgsProject, QgsWkbTypes

from .gpkg import (
    norm_path, INTERNAL_GROUP,
    gpkg_path_from_source, table_name_from_source,
)
from .fields import parse_field_value
from .lod import ogc_crs_uri, sf_class_from_names


def layer_gpkg_path(layer):
    """Extract the GPKG file path from an OGR layer's source string."""
    return gpkg_path_from_source(layer.source())


def layer_table_name(layer):
    """Extract the table name from an OGR layer's source string."""
    return table_name_from_source(layer.source())


def ensure_vocab_layer_loaded(gpkg_path, table_name):
    """
    Ensure a vocab attribute table from the GPKG is loaded as a QGIS layer
    inside the 'qskos [internal]' layer group (collapsed, not visible on canvas).

    Reuses the existing in-project layer if already loaded — safe to call
    multiple times.  Returns the QgsVectorLayer.

    The group is kept invisible so vocab tables don't clutter the map canvas,
    but ValueRelation widgets can still resolve the layer by ID from QgsProject.
    """
    norm_gpkg = norm_path(gpkg_path)

    # Reuse if already in project
    for layer in QgsProject.instance().mapLayers().values():
        if (
            layer_table_name(layer) == table_name
            and norm_path(layer_gpkg_path(layer)) == norm_gpkg
        ):
            return layer

    uri = f"{gpkg_path}|layername={table_name}"
    layer = QgsVectorLayer(uri, table_name, "ogr")
    if not layer.isValid():
        raise Exception(
            f"Failed to load vocab layer '{table_name}' from {gpkg_path}.\n"
            f"OGR error: {layer.error().message()}"
        )

    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup(INTERNAL_GROUP)
    if not group:
        group = root.insertGroup(0, INTERNAL_GROUP)

    QgsProject.instance().addMapLayer(layer, False)   # addToLegend=False
    group.addLayer(layer)
    group.setItemVisibilityChecked(False)
    group.setExpanded(False)

    return layer


def extract_layer_spec(layer, annotation_fields, object_id, object_label="",
                       object_type=""):
    """
    Extract the pure data structure for utils.lod.build_lod_graph from a QGIS
    feature layer. Reads each feature once, parses annotation field values, and
    captures geometry as WKT + CRS URI + sf class.

    Returns a spec dict with keys:
        object_id, object_label, object_type, features
    where each feature has: values, wkt, crs_uri, sf_class.
    """
    fields = layer.fields()
    crs_uri = ogc_crs_uri(layer.crs().authid() if layer.crs() else "")

    features = []
    for feat in layer.getFeatures():
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

        feat_data = {
            "values": values_by_field,
            "wkt": None,
            "crs_uri": crs_uri,
            "sf_class": None,
        }
        geom = feat.geometry()
        if geom and not geom.isNull() and not geom.isEmpty():
            geom_type = geom.type()
            type_name = {
                QgsWkbTypes.PolygonGeometry: "Polygon",
                QgsWkbTypes.PointGeometry: "Point",
                QgsWkbTypes.LineGeometry: "Line",
            }.get(geom_type)
            if type_name:
                feat_data["wkt"] = str(geom.asWkt())
                feat_data["sf_class"] = sf_class_from_names(
                    type_name, geom.isMultipart()
                )
        features.append(feat_data)

    return {
        "object_id": object_id,
        "object_label": object_label,
        "object_type": object_type,
        "features": features,
    }
