# qskos_utils.py
# qskos QGIS Plugin - Utility Functions
# Handles RDF/CSV parsing, tree generation, and descendant computation.

import csv
from qgis.core import QgsVectorLayer, QgsFeature, QgsField, QgsProject, QgsFeatureRequest
from PyQt5.QtWidgets import QTreeWidgetItem
from PyQt5.QtCore import Qt
import tempfile
import os

# Try to import rdflib. If not available, some functions will not work.
try:
    from rdflib import Graph, URIRef, Literal
    from rdflib.namespace import SKOS
    RDFLIB_AVAILABLE = True
except ImportError:
    RDFLIB_AVAILABLE = False


def load_skos_source(source_path_or_url, source_type, lang="en"):
    """
    Load SKOS data from RDF or CSV source.
    Returns a list of dicts with keys: 'skos:Concept', 'skos:prefLabel', 'skos:definition', 'skos:broader', 'skos:inScheme'
    Language preference is applied to prefLabel and definition.
    """
    if source_type in ['ttl', 'jsonld', 'url']:
        if not RDFLIB_AVAILABLE:
            raise ImportError("rdflib is required to load RDF sources.")
        return _load_from_rdf(source_path_or_url, source_type, lang)
    elif source_type == 'csv':
        return _load_from_csv(source_path_or_url, lang)
    else:
        raise ValueError(f"Unsupported source type: {source_type}")


def _load_from_rdf(source, source_format, lang="en"):
    """Load SKOS concepts from an RDF source using rdflib."""
    g = Graph()
    g.parse(source, format=source_format)

    # Collect unique concept subjects from both inScheme and topConceptOf
    seen_concepts = []
    for p in [SKOS.inScheme, SKOS.topConceptOf]:
        for s in g.subjects(p, None):
            if s not in seen_concepts:
                seen_concepts.append(s)

    # Build concept dictionaries
    concepts = []
    for concept in seen_concepts:
        concept_uri = str(concept)
        pref_label = _get_preferred_literal(g, concept, SKOS.prefLabel, lang)
        definition = _get_preferred_literal(g, concept, SKOS.definition, lang)
        broader = None
        for b in g.objects(concept, SKOS.broader):
            broader = str(b)
            break  # Take first broader for simplicity
        in_scheme = None
        for s in g.objects(concept, SKOS.inScheme):
            in_scheme = str(s)
            break

        concepts.append({
            'skos:Concept': concept_uri,
            'skos:prefLabel': pref_label or "",
            'skos:definition': definition or "",
            'skos:broader': broader,
            'skos:inScheme': in_scheme
        })
    return concepts


def _get_preferred_literal(graph, subject, predicate, preferred_lang="en"):
    """
    Get the best literal for a predicate: preferred_lang > 'en' > any other > first available.
    Returns plain string (no language tag).
    """
    candidates = []
    for obj in graph.objects(subject, predicate):
        if isinstance(obj, Literal):
            candidates.append((str(obj), obj.language))
        else:
            candidates.append((str(obj), None))

    # Priority: preferred_lang > 'en' > any with lang > any without lang > first
    for cand_text, cand_lang in candidates:
        if cand_lang == preferred_lang:
            return cand_text

    for cand_text, cand_lang in candidates:
        if cand_lang == "en":
            return cand_text

    for cand_text, cand_lang in candidates:
        if cand_lang is not None:
            return cand_text

    for cand_text, cand_lang in candidates:
        if cand_lang is None:
            return cand_text

    return candidates[0][0] if candidates else ""


def _load_from_csv(file_path, lang="en"):
    """Load SKOS concepts from a CSV file. Assumes pipe-separated multilingual fields."""
    concepts = []
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Normalize field names by stripping whitespace
            row = {k.strip(): v for k, v in row.items()}
            pref_label = _extract_label_by_language(row.get('skos:prefLabel', '').strip(), lang)
            definition = _extract_label_by_language(row.get('skos:definition', '').strip(), lang)

            concepts.append({
                'skos:Concept': row.get('skos:Concept', '').strip(),
                'skos:prefLabel': pref_label,
                'skos:definition': definition,
                'skos:broader': row.get('skos:broader', '').strip(),
                'skos:inScheme': row.get('skos:inScheme', '').strip()
            })
    return concepts


def _extract_label_by_language(label_str, lang="en"):
    """
    Extract label for given language from pipe-separated "label@lang" string.
    Fallback: en > any tagged > first untagged > first overall.
    """
    if not label_str:
        return ""

    parts = label_str.split('|')
    lang_map = {}
    plain_labels = []

    for part in parts:
        if '@' in part:
            txt, l = part.rsplit('@', 1)
            lang_map[l] = txt
        else:
            plain_labels.append(part)

    # Priority: selected lang > en > any lang > plain > first
    if lang in lang_map:
        return lang_map[lang]
    if "en" in lang_map:
        return lang_map["en"]
    if lang_map:
        return next(iter(lang_map.values()))
    if plain_labels:
        return plain_labels[0]
    return parts[0]


def convert_to_delimited_text_layer(concepts, scheme_uri, lang="en"):
    """
    Convert a list of concept dicts into a QGIS delimited text layer.
    Stores only the selected language’s prefLabel and definition.
    Returns the created QgsVectorLayer.
    """
    # Create a temporary CSV file — ensure it's fully written
    temp_csv = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8', newline='')
    fieldnames = ['skos:Concept', 'skos:prefLabel', 'skos:definition', 'skos:broader', 'skos:inScheme']

    # Use QUOTE_ALL to ensure fields with | or commas are safely quoted
    writer = csv.DictWriter(temp_csv, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    for concept in concepts:
        writer.writerow(concept)
    temp_csv.close()  # IMPORTANT: Close file so QGIS can read it

    # Build URI with explicit delimiter and quoting — disable detectTypes
    uri = (
        f"file:///{temp_csv.name}"
        "?type=csv"
        "&noGeometry=yes"
        "&crs=EPSG:4326"
        "&subsetIndex=no"
        "&watchFile=no"
        "&delimiter=,"           # Explicitly set delimiter
        "&quote=\\\""            # Escape quote char for URI
        "&skipEmptyFields=yes"
        "&trimFields=yes"
        # REMOVED: &detectTypes=yes — causes parsing failures
    )

    layer_name = scheme_uri.split('/')[-1] if '/' in scheme_uri else scheme_uri

    layer = QgsVectorLayer(uri, layer_name, "delimitedtext")
    if not layer.isValid():
        raise Exception(f"Failed to create delimited text layer from CSV: {layer.error().message()}")

    # Set custom properties
    layer.setCustomProperty("qskos:scheme", scheme_uri)
    layer.setCustomProperty("qskos:language", lang)

    # Add to project
    QgsProject.instance().addMapLayer(layer)
    return layer


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


def get_descendant_uris(vocab_layer, root_uri):
    """
    Recursively get all descendant URIs (including self) for a given root concept.
    Uses skos:broader to traverse upwards and find all children.
    """
    descendants = set()
    _collect_descendants(vocab_layer, root_uri, descendants)
    return list(descendants)


def _collect_descendants(vocab_layer, concept_uri, descendants):
    """Recursive helper to collect all descendants."""
    if concept_uri in descendants:
        return
    descendants.add(concept_uri)

    # Find all concepts that have this concept as their broader
    expr = f"\"skos:broader\" = '{concept_uri}'"
    request = QgsFeatureRequest().setFilterExpression(expr)
    for child_feature in vocab_layer.getFeatures(request):
        child_uri = child_feature['skos:Concept']
        _collect_descendants(vocab_layer, child_uri, descendants)


def get_filtered_descendant_uris(vocab_layer, root_uri):
    """
    Get all URIs that are descendants (children, grandchildren, etc.) of the given root concept.
    EXCLUDES the root concept itself.
    Ensures filter stays within the hierarchical branch defined by the root.
    """
    descendants = set()
    _collect_descendants(vocab_layer, root_uri, descendants)
    descendants.discard(root_uri)  # Explicitly exclude root
    return list(descendants)
    """
    Get all URIs that are either:
    - Siblings of the concept (same broader)
    - Descendants of the concept (children, grandchildren, etc.)
    EXCLUDES the concept itself.
    """
    target_uris = set()

    # Get the broader of the concept
    expr = f"\"skos:Concept\" = '{concept_uri}'"
    request = QgsFeatureRequest().setFilterExpression(expr)
    features = list(vocab_layer.getFeatures(request))
    if not features:
        return []

    broader_uri = features[0]['skos:broader']

    # Find all siblings (same broader, excluding self)
    if broader_uri:
        sibling_expr = f"\"skos:broader\" = '{broader_uri}' AND \"skos:Concept\" != '{concept_uri}'"
    else:
        # Root-level siblings: all top concepts except self
        sibling_expr = f"(\"skos:broader\" IS NULL OR \"skos:broader\" = '') AND \"skos:Concept\" != '{concept_uri}'"

    sibling_request = QgsFeatureRequest().setFilterExpression(sibling_expr)
    for feat in vocab_layer.getFeatures(sibling_request):
        target_uris.add(feat['skos:Concept'])

    # Add all descendants of the concept (excluding self — handled in recursion start)
    descendants = set()
    _collect_descendants(vocab_layer, concept_uri, descendants)
    descendants.discard(concept_uri)  # Explicitly exclude self
    target_uris.update(descendants)

    return list(target_uris)