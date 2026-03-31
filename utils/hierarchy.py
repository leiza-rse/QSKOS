# hierarchy.py
# qskos QGIS Plugin - Hierarchy Utilities
# Tree building, hierarchy index, and descendant BFS.
# Language is baked into the prefLabel column at GPKG import time —
# no language parameter is needed here.

from PyQt5.QtWidgets import QTreeWidgetItem
from PyQt5.QtCore import Qt


def build_concept_tree_from_layer(vocab_layer):
    """
    Build QTreeWidgetItems from a vocab OGR layer (loaded from GPKG).
    Returns root items (concepts with no broader).

    Two-pass approach:
      Pass 1 — create one QTreeWidgetItem per concept.
      Pass 2 — attach children to parents; collect roots.
    """
    concepts   = {}
    root_items = []

    # Pass 1: create items
    for feat in vocab_layer.getFeatures():
        uri   = feat["concept"]
        label = feat["prefLabel"]
        item  = QTreeWidgetItem([label])
        item.setData(0, Qt.UserRole, uri)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Unchecked)
        concepts[uri] = item

    # Pass 2: wire hierarchy
    for feat in vocab_layer.getFeatures():
        uri     = feat["concept"]
        broader = feat["broader"] or None
        item    = concepts.get(uri)
        if item is None:
            continue
        if broader and broader in concepts:
            concepts[broader].addChild(item)
        else:
            root_items.append(item)

    return root_items


def build_hierarchy_index(vocab_layer):
    """
    Precompute the hierarchy from a vocab OGR layer.

    Returns:
        children_map   — {parent_uri: [child_uri, ...], None: [root_uri, ...]}
        concept_labels — {uri: prefLabel}

    None is used as the key for root concepts (those with no broader).
    """
    children_map   = {None: []}
    concept_labels = {}

    for feat in vocab_layer.getFeatures():
        uri     = feat["concept"]
        broader = feat["broader"] or None
        label   = feat["prefLabel"]

        concept_labels[uri] = label
        if broader not in children_map:
            children_map[broader] = []
        children_map[broader].append(uri)

    return children_map, concept_labels


def get_descendant_uris_fast(children_map, root_uri):
    """
    BFS from root_uri, returning all descendants including root itself.
    Safe for leaf nodes — returns [root_uri] when no children key exists.
    """
    descendants, queue = set(), [root_uri]
    while queue:
        current = queue.pop(0)
        if current in descendants:
            continue
        descendants.add(current)
        for child in children_map.get(current, []):
            if child not in descendants:
                queue.append(child)
    return list(descendants)


def get_filtered_descendant_uris_fast(children_map, root_uri):
    """Descendants of root_uri, excluding the root itself."""
    descendants = get_descendant_uris_fast(children_map, root_uri)
    if root_uri in descendants:
        descendants.remove(root_uri)
    return descendants