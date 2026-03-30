# hierarchy.py
# qskos QGIS Plugin - Hierarchy Utilities
# Handles tree building, hierarchy index, and descendant computation.

from PyQt5.QtWidgets import QTreeWidgetItem
from PyQt5.QtCore import Qt


def build_concept_tree_from_layer(vocab_layer, lang="en"):
    """
    Build a list of QTreeWidgetItems representing the SKOS hierarchy.
    Uses stored language preference from layer custom property if available.
    Returns root items (concepts with no broader).
    """
    # Override lang if layer has stored preference
    stored_lang = vocab_layer.customProperty("qskos:language")
    if stored_lang:
        lang = stored_lang

    concepts = {}
    root_items = []

    # First pass: create all items
    for feature in vocab_layer.getFeatures():
        concept_uri = feature['skos:Concept']
        label = feature['skos:prefLabel']  # Already filtered by language during load
        item = QTreeWidgetItem([label])
        item.setData(0, Qt.UserRole, concept_uri)  # Store URI in UserRole
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Unchecked)
        concepts[concept_uri] = item

    # Second pass: build hierarchy
    for feature in vocab_layer.getFeatures():
        concept_uri = feature['skos:Concept']
        broader_uri = feature['skos:broader']
        item = concepts[concept_uri]

        if broader_uri and broader_uri in concepts:
            concepts[broader_uri].addChild(item)
        else:
            root_items.append(item)

    return root_items


# 👇 NEW: Precomputed hierarchy index
def build_hierarchy_index(vocab_layer):
    """
    Precompute a dict: parent_uri → [child_uri1, child_uri2, ...]
    Includes None as key for root concepts.
    Returns: children_map, concept_labels (uri → label)
    """
    children_map = {}
    concept_labels = {}

    # Initialize with None for root concepts
    children_map[None] = []

    for feat in vocab_layer.getFeatures():
        uri = feat['skos:Concept']
        broader = feat['skos:broader'] or None  # Treat empty string as None
        label = feat['skos:prefLabel']

        concept_labels[uri] = label

        if broader not in children_map:
            children_map[broader] = []
        children_map[broader].append(uri)

    return children_map, concept_labels


# 👇 NEW: Fast descendant collection using precomputed index
def get_descendant_uris_fast(children_map, root_uri):
    """
    Get all descendants (including self) using precomputed children_map.
    Uses BFS to avoid recursion depth issues.
    """
    # --- REMOVED INCORRECT CHECK ---
    # The previous check `if root_uri not in children_map and root_uri not in children_map.get(None, []):`
    # was incorrect because:
    # 1. Leaf concepts are not KEYS in children_map (they have no children).
    # 2. Leaf concepts might not be in children_map[None] (unless they are also roots).
    # This caused the function to incorrectly return [] for valid leaf URIs.
    # The BFS logic below correctly handles finding descendants (or just self if no children).

    descendants = set()
    queue = [root_uri]
    while queue:
        current = queue.pop(0)
        if current in descendants:
            continue
        descendants.add(current)
        # Add direct children
        # children_map.get(current, []) handles cases where current is not a parent key
        children_list = children_map.get(current, [])
        for child in children_list:
            if child not in descendants:
                queue.append(child)
    return list(descendants)


def get_filtered_descendant_uris_fast(children_map, root_uri):
    """
    Get descendants excluding root.
    """
    descendants = get_descendant_uris_fast(children_map, root_uri)
    if root_uri in descendants:
        descendants.remove(root_uri)
    return descendants