# annotation.py
# qskos QGIS Plugin - Annotation field management
# Creation and (re)configuration of annotation fields and their ValueRelation
# editor widget.
#
# An annotation field is named after a concept URI and stored as a GeoPackage
# JSON field (QVariant.Map).  Its ValueRelation widget offers that concept and
# all its descendants and writes the selection as a JSON array, which the
# symbology rules query with array_intersect().  (A text field would make the
# widget write '{"a","b"}', which the array functions cannot read.)
#
# build_value_relation_config is pure; the rest are thin QGIS adapters.

from PyQt5.QtCore import QVariant
from qgis.core import QgsField, QgsEditorWidgetSetup, QgsDefaultValue

from .hierarchy import get_descendant_uris_fast
from .fields import find_annotation_field_names
from .gpkg import (
    F_CONCEPT, F_LABEL, F_DEF, VOCAB_PROPERTY,
    find_vocab_table_for_scheme, get_bound_vocab_schemes, has_qskos_config,
)
from .layers import ensure_vocab_layer_loaded, layer_gpkg_path, layer_table_name
from .logging import log, LEVEL_WARNING


# ── Pure helpers (unit-testable, no QGIS) ─────────────────────────────────────

def build_value_relation_config(vocab_layer_id, children_map, concept_uri,
                                layer_name="", layer_source=""):
    """
    Build the ValueRelation editor config for an annotation field on a concept.

    The widget offers concept_uri itself plus all of its descendants from the
    vocabulary, storing the concept URI and showing prefLabel.  Including the
    concept itself means a leaf concept still offers one value.

    vocab_layer_id is the QGIS layer id; layer_name / layer_source let QGIS
    re-resolve the vocab layer when the id no longer matches (e.g. the layer
    was removed and re-added to the project).
    """
    target_uris = get_descendant_uris_fast(children_map, concept_uri)
    quoted = ["'" + u.replace("'", "''") + "'" for u in target_uris]
    filter_expression = f'"{F_CONCEPT}" IN ({",".join(quoted)})'

    return {
        "Layer":             vocab_layer_id,
        "LayerName":         layer_name,
        "LayerSource":       layer_source,
        "LayerProviderName": "ogr",
        "Key":               F_CONCEPT,   # stored value: concept URI
        "Value":             F_LABEL,     # displayed: prefLabel
        "Description":       F_DEF,       # tooltip: definition
        "FilterExpression":  filter_expression,
        "AllowMulti":        True,
        "UseCompleter":      True,
        "OrderByValue":      True,
    }


# ── QGIS adapters ─────────────────────────────────────────────────────────────

def _config_for(vocab_layer, children_map, concept_uri):
    return build_value_relation_config(
        vocab_layer.id(), children_map, concept_uri,
        vocab_layer.name(), vocab_layer.source(),
    )


def _apply_widget(feature_layer, field_index, vocab_layer, children_map,
                  concept_uri, label):
    config = _config_for(vocab_layer, children_map, concept_uri)
    current = feature_layer.editorWidgetSetup(field_index)
    # Unchanged widgets are left alone, so opening a project does not mark it
    # as modified.
    if current.type() != "ValueRelation" or current.config() != config:
        feature_layer.setEditorWidgetSetup(
            field_index, QgsEditorWidgetSetup("ValueRelation", config)
        )
    if feature_layer.attributeAlias(field_index) != label:
        feature_layer.setFieldAlias(field_index, label)


def create_annotation_field(feature_layer, vocab_layer, children_map,
                            concept_uri, label):
    """
    Add a JSON annotation field named concept_uri to feature_layer, configured
    with a ValueRelation widget listing the concept and its descendants.

    If the layer is already in edit mode the field is added to the user's
    edit session and NOT committed (committing would also save the user's
    unrelated pending edits); it is written when the user saves.  Otherwise
    the field is added and committed straight away.

    Returns "exists", "created" or "pending" (added to an open edit session).
    Raises RuntimeError if QGIS refuses the change.
    """
    if feature_layer.fields().lookupField(concept_uri) != -1:
        return "exists"

    was_editing = feature_layer.isEditable()
    if not was_editing and not feature_layer.startEditing():
        raise RuntimeError(f"Layer '{feature_layer.name()}' cannot be edited.")

    # Must match the GPKG provider's native JSON type exactly (type Map,
    # typeName "JSON", subType String), or commitChanges() rejects the new
    # field with "field ... is not the same" although the column was added.
    field = QgsField(concept_uri, QVariant.Map, "JSON", 0, 0, "", QVariant.String)
    if not feature_layer.addAttribute(field):
        if not was_editing:
            feature_layer.rollBack()
        raise RuntimeError(f"Could not add field '{concept_uri}'.")
    feature_layer.updateFields()

    field_index = feature_layer.fields().lookupField(concept_uri)
    feature_layer.setDefaultValueDefinition(
        field_index, QgsDefaultValue("array()", False)
    )
    _apply_widget(feature_layer, field_index, vocab_layer, children_map,
                  concept_uri, label)

    if was_editing:
        return "pending"
    if not feature_layer.commitChanges():
        errors = "; ".join(feature_layer.commitErrors())
        feature_layer.rollBack()
        raise RuntimeError(f"Could not save field '{concept_uri}': {errors}")
    return "created"


def reconfigure_annotation_field(feature_layer, vocab_layer, children_map,
                                 concept_uri, label):
    """
    Re-point an existing annotation field's ValueRelation widget to the
    concept and its descendants. Returns True if the field was found and
    reconfigured, False otherwise.
    """
    field_index = feature_layer.fields().lookupField(concept_uri)
    if field_index == -1:
        return False

    _apply_widget(feature_layer, field_index, vocab_layer, children_map,
                  concept_uri, label)
    return True


def reinitialize_annotation_fields_for_vocab(feature_layer, vocab_layer,
                                             children_map, concept_labels):
    """
    Reconfigure every existing annotation field on feature_layer that belongs to
    this vocabulary (i.e. whose field name is a concept in concept_labels).
    """
    field_names = [f.name() for f in feature_layer.fields()]
    for name in find_annotation_field_names(field_names, concept_labels):
        reconfigure_annotation_field(
            feature_layer, vocab_layer, children_map, name, concept_labels[name]
        )


def bind_annotation_widgets(feature_layer, get_hierarchy):
    """
    Load every vocabulary bound to feature_layer (as hidden layers) and point
    its annotation fields' widgets at them.  The widgets read their options
    from those layers, so without this a form opened before the Layer tab was
    used shows no options.

    Does nothing for layers that are not in a GeoPackage with qskos bindings.
    get_hierarchy: vocab_layer -> (children_map, concept_labels), i.e.
    QskosState.get_hierarchy_for_layer.
    """
    table = layer_table_name(feature_layer)
    gpkg_path = layer_gpkg_path(feature_layer)
    if not table or not has_qskos_config(gpkg_path):
        return
    for scheme_uri in get_bound_vocab_schemes(gpkg_path, table):
        vocab_table = find_vocab_table_for_scheme(gpkg_path, scheme_uri)
        if not vocab_table:
            continue
        try:
            vocab_layer = ensure_vocab_layer_loaded(gpkg_path, vocab_table)
            children_map, labels = get_hierarchy(vocab_layer)
            reinitialize_annotation_fields_for_vocab(
                feature_layer, vocab_layer, children_map, labels
            )
        except Exception as e:
            log(f"Cannot bind annotation widgets for {scheme_uri}: {e}",
                LEVEL_WARNING)


def bind_all_annotation_widgets(get_hierarchy):
    """bind_annotation_widgets for every vector layer of the project except
    the vocabulary copies themselves."""
    from qgis.core import QgsMapLayer, QgsProject
    for layer in list(QgsProject.instance().mapLayers().values()):
        if layer.type() == QgsMapLayer.VectorLayer and not layer.customProperty(VOCAB_PROPERTY):
            bind_annotation_widgets(layer, get_hierarchy)
