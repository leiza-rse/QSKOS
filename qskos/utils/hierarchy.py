# hierarchy.py
# qskos QGIS Plugin - Hierarchy Utilities
# Pure, QGIS-free functions: hierarchy index building and descendant BFS.
# The Qt tree-widget builder (build_concept_tree_items) lives in
# tabs/layer.py; this module intentionally has no Qt/QGIS imports so it can be
# unit-tested without a QGIS runtime.
# Language is baked into the prefLabel column at GPKG import time — no language
# parameter is needed here.


def build_hierarchy_index(vocab_layer):
    """
    Precompute the hierarchy from a vocab layer.

    Returns:
        children_map   — {parent_uri: [child_uri, ...], None: [root_uri, ...]}
        concept_labels — {uri: prefLabel}

    None is used as the key for root concepts (those with no broader).
    vocab_layer must be an iterable of features exposing 'concept', 'broader',
    'prefLabel' (a QGIS vector layer, or a fake in tests).
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
