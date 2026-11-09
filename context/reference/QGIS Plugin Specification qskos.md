#  QGIS Plugin Specification: `qskos`

## 1. Environment

- **Target Platform**: QGIS 3.40.7 — Bratislava
- **Language**: Python 3 with PyQt5 / PyQGIS
- **RDF Handling**: `rdflib` for parsing SKOS hierarchies
- **CSV Handling**: Standard `csv` module with UTF-8 encoding and proper quoting

---

## 2. Purpose

The **qskos** plugin enables **semantic annotation of vector layer features** using concepts from **SKOS vocabularies**. It supports:

- Loading SKOS vocabularies from local/remote RDF or CSV and saving them as delimited text layers (noGeometry=yes)
- Binding vocabulary layers to vector layers via custom properties
- Creating annotation fields based on selected subtrees in vocabulary treeview
- Configuring **Value Relation widgets** with filtered concept options (descendants of subtree roots only)
- Supporting **German (`@de`) labels with English (`@en`) as fallback

>  The plugin treats SKOS vocabularies as **controlled vocabularies** for attribute annotation and potential rule-based symbology.

---

## 3. Vocabulary Tab – Load and Convert SKOS Sources

### 3.1 Supported Sources

-  **Local RDF files**: `.ttl` (Turtle), `.jsonld` (JSON-LD)
-  **Remote RDF resources**: Raw Turtle or JSON-LD via URL
-  **Local CSV files**: With specific column structure

### 3.2 CSV Format (Required Columns for loading as CSV and saving as layer)

| Column | Description |
| `skos:Concept` | URI of the concept |
| `skos:prefLabel` | Preferred labels, language-tagged with `@de`, `@en`, etc. When loading from csv multiple labels can be pipe-separated. Saving as @de or @en fallback | 
| `skos:definition` | Definitions with language tags (language tags and pipe-separation like prefLabel) |
| `skos:broader` | parent concept URI |
| `skos:inScheme` | URI of the concept scheme (optional) |

### 3.3 Conversion to Delimited Text Layer

Each vocabulary is converted into a **non-geometric delimited text layer** with:

- **Columns**: `skos:Concept`, `skos:prefLabel`, `skos:definition`, `skos:broader`, `skos:inScheme`
- **Layer Name**: Derived from ConceptScheme URI (full URI if possible)
- **Custom Property**: `qskos:scheme` = full ConceptScheme URI
- **Data Provider**: `delimitedtext` with:
  - `noGeometry=yes`
  - `crs=EPSG:4326` (required even for non-geometry)
  - `type=csv`
  - `trimFields=yes`, `detectTypes=yes`

---

## 4. Layer Tab – Bind Layers & Manage Annotation Fields

### 4.1 Layer Selection and Binding

- **Vector Layer Dropdown**: Shows only **vector layers with geometry** (excludes delimited text layers)
- **Vocabulary Layer Dropdown**: Shows only **delimited text layers with `qskos:scheme`** set
- **Bind Button**: Creates a binding using **custom properties**, 

####  Binding Mechanism (Custom Properties)

| Layer Type | Property | Value |
|----------|---------|-------|
| **Vocabulary Layer** | `qskos:scheme` | Full ConceptScheme URI |
| **Feature Layer** | `qskos:binding` | Same ConceptScheme URI (points to bound vocabulary) |

---

### 4.2 Tree View of Concepts

When a selected feature layer is bound to a vocabulary:
- A **tree view** displays the concept hierarchy using the binded delimited text vocabulary layer and its `skos:broader` relations
- **Labels**: skos_prefLabel
- **Checkboxes**: Each concept can be checked to create an annotation field for the feature layer

---

### 4.3 Field Creation from Checked Concepts for feature layer

When a concept is **checked**:
1. A new field is created with:
   - **Name**: concept URI (full URI if possible)
   - **Type**: `Map` (stored as JSON)
   - **Alias**: Concept’s preferred label
   - **Widget**: `ValueRelation` with binded delimited text vocabulary layer
   - **Existing fields**: existing fields with name = URI result in already checked boxes

2. The **Value Relation** is configured to show only **descendants** of the concept (including itself)

####  Descendant Filtering

- **Computed using recursive `skos:broader` of the binded delimited text vocabulary layer
- **Filter Expression**:  
  "skos:Concept" IN ('uri1', 'uri2', ...)
   - Ensures only relevant concepts appear in the widget

####  Value Relation Configuration

| Setting | Value |
|-------|-------|
| Layer | Vocabulary delimited text layer |
| Key | `skos:Concept` |
| Value | `skos:prefLabel` |
| Description | `skos:definition` |
| Filter | `"skos:Concept" IN (...)"`
| Allow Multi | `True` |
| Use Completer | `True` |

---

## 5. Dynamic Updates & UX Improvements

### 5.1 Auto-Refresh Layer Dropdowns

- Listens to `QgsProject.instance().layerWasAdded` and `layerWillBeRemoved`
- Uses `QTimer.singleShot(0, self.refresh)` to avoid reentrancy
- Updates both dropdowns **live** when layers are added

---
## 6. Rule-Based Symbology
-	Auto-generate rules for concepts used as value in annotation fields
-	Include ancestors of the annotated concepts

## 7. Python Script starting point
Use this minimal qgis plugin script as starting point

from PyQt5.QtWidgets import QAction, QMessageBox

def classFactory(iface):
    return MinimalPlugin(iface)

class MinimalPlugin:
    def __init__(self, iface):
        self.iface = iface

    def initGui(self):
        self.action = QAction('Go!', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        self.iface.removeToolBarIcon(self.action)
        del self.action

    def run(self):
        QMessageBox.information(None, 'Minimal plugin', 'Do something useful here')


## 7. Future Enhancements (Optional)

| Feature | Description |
|-------|-------------|
| 📤 Export Annotations to RDF | Serialize as SKOS-XL or custom ontology |
