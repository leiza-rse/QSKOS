# annotation.py
# qskos QGIS Plugin - Annotation field management
# Owns the detection, creation and reconfiguration of annotation fields and the
# ValueRelation editor widget setup. This centralises the logic that used to be
# copy-pasted across tabs/layer.py (create_annotation_field, _reconfigure_...,
# reinitialize_all_...).
#
# The pure helpers (build_value_relation_config, find_annotation_field_names)
# have no QGIS imports and are unit-tested. The QGIS-touching functions are thin
# adapters over them plus the field/editor API.

from PyQt5.QtCore import QVariant
from qgis.core import QgsField, QgsEditorWidgetSetup, QgsDefaultValue

from .hierarchy import get_filtered_descendant_uris_fast
from .fields import find_annotation_field_names
from .gpkg import F_CONCEPT, F_LABEL, F_DEF


# ── Pure helpers (unit-testable, no QGIS) ─────────────────────────────────────

def build_value_relation_config(vocab_layer_id, children_map, concept_uri):
    """
    Build the ValueRelation editor config for an annotation field on a concept.

    The widget offers the descendants of concept_uri (excluding the concept
    itself) from the vocabulary, storing the concept URI and showing prefLabel.
    vocab_layer_id is the (volatile) QGIS layer id resolved at creation time.
    """
    target_uris = get_filtered_descendant_uris_fast(children_map, concept_uri)
    if not target_uris:
        filter_expression = "0"   # concept has no descendants — nothing to pick
    else:
        quoted = ["'" + u.replace("'", "''") + "'" for u in target_uris]
        filter_expression = f'"{F_CONCEPT}" IN ({",".join(quoted)})'

    return {
        "Layer":            vocab_layer_id,
        "Key":              F_CONCEPT,   # stored value: concept URI
        "Value":            F_LABEL,     # displayed: prefLabel
        "Description":      F_DEF,       # tooltip: definition
        "FilterExpression": filter_expression,
        "AllowMulti":       True,
        "UseCompleter":     True,
        "OrderByValue":     True,
    }


# ── QGIS adapters ─────────────────────────────────────────────────────────────

def create_annotation_field(feature_layer, vocab_layer, children_map,
                            concept_uri, label):
    """
    Add a text annotation field named concept_uri to feature_layer, configured
    with a ValueRelation widget listing the concept's descendants. Returns True
    if a new field was created, False if it already existed.
    """
    if feature_layer.fields().lookupField(concept_uri) != -1:
        return False

    feature_layer.startEditing()
    feature_layer.addAttribute(QgsField(concept_uri, QVariant.String))
    feature_layer.updateFields()

    field_index = feature_layer.fields().lookupField(concept_uri)
    feature_layer.setDefaultValueDefinition(
        field_index, QgsDefaultValue("'[]'", False)
    )

    config = build_value_relation_config(vocab_layer.id(), children_map, concept_uri)
    feature_layer.setEditorWidgetSetup(
        field_index, QgsEditorWidgetSetup("ValueRelation", config)
    )
    feature_layer.setFieldAlias(field_index, label)
    feature_layer.commitChanges()
    return True


def reconfigure_annotation_field(feature_layer, vocab_layer, children_map,
                                 concept_uri, label):
    """
    Re-point an existing annotation field's ValueRelation widget to the
    descendants of concept_uri. Returns True if the field was found and
    reconfigured, False otherwise.
    """
    field_index = feature_layer.fields().lookupField(concept_uri)
    if field_index == -1:
        return False

    config = build_value_relation_config(vocab_layer.id(), children_map, concept_uri)
    feature_layer.setEditorWidgetSetup(
        field_index, QgsEditorWidgetSetup("ValueRelation", config)
    )
    feature_layer.setFieldAlias(field_index, label)
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
