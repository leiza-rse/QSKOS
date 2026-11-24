# layers.py
# qskos QGIS Plugin - QGIS layer adapter
# Thin adapters over QGIS vector layers: path/table extraction and loading a
# hidden in-memory copy of a vocabulary table into the project (ADR-0007).  They need QGIS, so they live apart
# from the pure data-access layer (utils/gpkg.py).  The LOD export adapter is
# utils/lod.py (QGIS) on top of the pure model in utils/rdf_model.py.

from qgis.core import QgsFeature, QgsVectorLayer, QgsProject

from .gpkg import (
    norm_path, INTERNAL_GROUP, VOCAB_FIELDS, VOCAB_PROPERTY,
    gpkg_path_from_source, read_vocab_rows, table_name_from_source,
    vocab_source_key,
)


def layer_gpkg_path(layer):
    """Extract the GPKG file path from an OGR layer's source string."""
    return gpkg_path_from_source(layer.source())


def layer_table_name(layer):
    """Extract the table name from an OGR layer's source string."""
    return table_name_from_source(layer.source())


def _vocab_copies():
    """{vocab source key: [in-memory copies in the project]}"""
    copies = {}
    for layer in QgsProject.instance().mapLayers().values():
        key = layer.customProperty(VOCAB_PROPERTY)
        if key:
            copies.setdefault(key, []).append(layer)
    return copies


def _preferred(copies):
    # A filled copy beats one that a saved project restored empty.
    return max(copies, key=lambda layer: layer.featureCount())


def find_vocab_layer(gpkg_path, table_name):
    """The project's in-memory copy of a vocabulary table, or None."""
    copies = _vocab_copies().get(vocab_source_key(gpkg_path, table_name))
    return _preferred(copies) if copies else None


def remove_duplicate_vocab_layers():
    """
    Keep one copy per vocabulary table.  While a saved project loads, a copy
    can be created before the project's own (empty) one is restored.  Never
    call this while a project is being read (removing a layer QGIS is still
    loading crashes it); afterwards re-point the widgets
    (annotation.bind_all_annotation_widgets).
    """
    extra = [
        layer.id()
        for copies in _vocab_copies().values()
        for layer in copies if layer is not _preferred(copies)
    ]
    if extra:
        QgsProject.instance().removeMapLayers(extra)


def _fill_vocab_layer(layer, gpkg_path, table_name):
    """Replace the layer's features with the table's current rows."""
    rows = read_vocab_rows(gpkg_path, table_name)
    provider = layer.dataProvider()
    provider.truncate()
    features = []
    for row in rows:
        feat = QgsFeature(layer.fields())
        feat.setAttributes(list(row))
        features.append(feat)
    if not provider.addFeatures(features) or provider.featureCount() != len(rows):
        raise RuntimeError(
            f"Could not copy vocabulary '{table_name}': "
            f"{provider.featureCount()} of {len(rows)} concepts. "
            + "; ".join(provider.errors()))
    layer.updateExtents()
    layer.dataChanged.emit()


def _remove_legacy_vocab_layers(gpkg_path, table_name):
    """Drop GPKG-backed vocab layers that older builds put in the internal group."""
    group = QgsProject.instance().layerTreeRoot().findGroup(INTERNAL_GROUP)
    if not group:
        return
    norm_gpkg = norm_path(gpkg_path)
    stale = [
        node.layerId() for node in group.findLayers()
        if node.layer() is not None
        and layer_table_name(node.layer()) == table_name
        and norm_path(layer_gpkg_path(node.layer())) == norm_gpkg
    ]
    if stale:
        QgsProject.instance().removeMapLayers(stale)


def ensure_vocab_layer_loaded(gpkg_path, table_name, refresh=False):
    """
    Return the hidden in-memory copy of a vocabulary table, creating it in the
    collapsed, invisible 'qskos [internal]' group if needed.  Trees and
    ValueRelation widgets read this copy, never the GPKG layer: QGIS's shared
    GeoPackage connection can go stale while another layer of the same file
    is edited, and then returns no rows (ADR-0007).  The GPKG stays the source
    of truth; refresh=True re-reads it (after an import).  A copy that a saved
    project brought back empty is refilled.  Safe to call repeatedly.
    """
    layer = find_vocab_layer(gpkg_path, table_name)
    if layer is not None and any(f.length() > 0 for f in layer.fields()):
        # A copy from a test build, capped at 255 characters: replace it.
        QgsProject.instance().removeMapLayer(layer.id())
        layer = None
    if layer is not None:
        if refresh or layer.featureCount() == 0:
            _fill_vocab_layer(layer, gpkg_path, table_name)
        return layer

    # string(0): no length limit (a bare 'string' is capped at 255 characters
    # and the provider silently rejects longer definitions).
    fields = "&".join(f"field={name}:string(0)" for name in VOCAB_FIELDS)
    layer = QgsVectorLayer(f"None?{fields}", table_name, "memory")
    if not layer.isValid():
        raise RuntimeError(f"Could not create a layer for vocabulary '{table_name}'.")
    layer.setCustomProperty(VOCAB_PROPERTY, vocab_source_key(gpkg_path, table_name))
    # A cache, not user data: QGIS need not warn that it is not saved.
    layer.setCustomProperty("skipMemoryLayersCheck", 1)
    _fill_vocab_layer(layer, gpkg_path, table_name)
    _remove_legacy_vocab_layers(gpkg_path, table_name)

    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup(INTERNAL_GROUP)
    if not group:
        group = root.insertGroup(0, INTERNAL_GROUP)

    QgsProject.instance().addMapLayer(layer, False)   # addToLegend=False
    group.addLayer(layer)
    group.setItemVisibilityChecked(False)
    group.setExpanded(False)

    return layer
