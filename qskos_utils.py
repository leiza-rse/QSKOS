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


def load_skos_source(source_path_or_url, source_type):
    """
    Load SKOS data from RDF or CSV source.
    Returns a list of dicts with keys: 'skos:Concept', 'skos:prefLabel', 'skos:definition', 'skos:broader', 'skos:inScheme'
    """
    if source_type in ['ttl', 'jsonld', 'url']:
        if not RDFLIB_AVAILABLE:
            raise ImportError("rdflib is required to load RDF sources.")
        return _load_from_rdf(source_path_or_url, source_type)
    elif source_type == 'csv':
        return _load_from_csv(source_path_or_url)
    else:
        raise ValueError(f"Unsupported source type: {source_type}")


def _load_from_rdf(source, source_format):
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
        pref_labels = _get_language_map(g, concept, SKOS.prefLabel)
        definitions = _get_language_map(g, concept, SKOS.definition)
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
            'skos:prefLabel': pref_labels,
            'skos:definition': definitions,
            'skos:broader': broader,
            'skos:inScheme': in_scheme
        })
    return concepts


def _get_language_map(graph, subject, predicate):
    """Helper to get language-tagged literals as a pipe-separated string."""
    literals = []
    for obj in graph.objects(subject, predicate):
        if isinstance(obj, Literal) and obj.language:
            literals.append(f"{obj}@{obj.language}")
        else:
            literals.append(str(obj))
    return "|".join(literals)


def _load_from_csv(file_path):
    """Load SKOS concepts from a CSV file."""
    concepts = []
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Normalize field names by stripping whitespace
            row = {k.strip(): v for k, v in row.items()}
            concepts.append({
                'skos:Concept': row.get('skos:Concept', '').strip(),
                'skos:prefLabel': row.get('skos:prefLabel', '').strip(),
                'skos:definition': row.get('skos:definition', '').strip(),
                'skos:broader': row.get('skos:broader', '').strip(),
                'skos:inScheme': row.get('skos:inScheme', '').strip()
            })
    return concepts


def convert_to_delimited_text_layer(concepts, scheme_uri):
    """
    Convert a list of concept dicts into a QGIS delimited text layer.
    Returns the created QgsVectorLayer.
    """
    # Create a temporary CSV file
    temp_csv = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8', newline='')
    fieldnames = ['skos:Concept', 'skos:prefLabel', 'skos:definition', 'skos:broader', 'skos:inScheme']

    writer = csv.DictWriter(temp_csv, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()
    for concept in concepts:
        writer.writerow(concept)
    temp_csv.close()

    # Create layer URI
    uri = f"file:///{temp_csv.name}?type=csv&noGeometry=yes&crs=EPSG:4326&trimFields=yes&detectTypes=yes"
    layer_name = scheme_uri.split('/')[-1] if '/' in scheme_uri else scheme_uri

    layer = QgsVectorLayer(uri, layer_name, "delimitedtext")
    if not layer.isValid():
        raise Exception("Failed to create delimited text layer from CSV.")

    # Set custom property
    layer.setCustomProperty("qskos:scheme", scheme_uri)

    # Add to project
    QgsProject.instance().addMapLayer(layer)
    return layer


def build_concept_tree_from_layer(vocab_layer):
    """
    Build a list of QTreeWidgetItems representing the SKOS hierarchy.
    Returns root items (concepts with no broader).
    """
    concepts = {}
    root_items = []

    # First pass: create all items
    for feature in vocab_layer.getFeatures():
        concept_uri = feature['skos:Concept']
        label = _get_preferred_label(feature['skos:prefLabel'])
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


def _get_preferred_label(pref_label_str):
    """
    Extract preferred label: German (@de) with English (@en) fallback.
    Input is a pipe-separated string of "label@lang" or plain labels.
    """
    if not pref_label_str:
        return ""

    labels = pref_label_str.split('|')
    de_labels = [lbl.rsplit('@', 1)[0] for lbl in labels if lbl.endswith('@de')]
    en_labels = [lbl.rsplit('@', 1)[0] for lbl in labels if lbl.endswith('@en')]
    plain_labels = [lbl for lbl in labels if '@' not in lbl]

    if de_labels:
        return de_labels[0]
    elif en_labels:
        return en_labels[0]
    elif plain_labels:
        return plain_labels[0]
    else:
        return labels[0] if labels else ""


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
        