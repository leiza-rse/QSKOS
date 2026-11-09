# layers.py
# qskos QGIS Plugin - QGIS layer adapter
# Thin adapters over QGIS vector layers: path/table extraction and loading a
# hidden vocab layer into the project.  They need QGIS, so they live apart
# from the pure data-access layer (utils/gpkg.py).  The LOD export adapter is
# utils/lod.py (QGIS) on top of the pure model in utils/rdf_model.py.

from qgis.core import QgsVectorLayer, QgsProject

from .gpkg import (
    norm_path, INTERNAL_GROUP,
    gpkg_path_from_source, table_name_from_source,
)


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
