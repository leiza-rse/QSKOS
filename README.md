# QSKOS Plugin - Semantic Annotation for QGIS

## Installation

To install the QSKOS plugin in QGIS:

1. **Download the plugin**: Click on the green "<> Code" button on the GitHub repository page and select "Download ZIP" from the popout menu.
2. **Install in QGIS**: In QGIS, go to Plugins → Manage and Install Plugins → Install From Zip.
3. **Select the ZIP file**: In the file picker, navigate to and select the downloaded ZIP file.
4. **Complete installation**: Click on "Install Plugin" and accept the security warning by clicking "Yes".

The plugin bundles the pure-Python libraries it needs to read RDF vocabularies (rdflib and its dependencies) inside its `libs/` folder, so no manual `pip install` is required.

## What is QSKOS?

QSKOS is a QGIS plugin that enables semantic annotation of geographic features using controlled vocabularies. It allows you to add meaningful, standardized labels and descriptions to your vector data layers, with all data stored directly in GeoPackage files.

## Use Case

The plugin is designed for researchers who need to:
- Add semantic meaning to geographic features
- Use standardized vocabularies for consistent data annotation
- Enable better data discovery and interoperability
- Work with portable, self-contained GeoPackage files

## Basic Functions

### 1. GeoPackage Selection (First Step)
- **NEW**: Select a GeoPackage file as your data container
- All plugin data (vocabularies, configurations, annotations) are stored in the GeoPackage
- The GeoPackage becomes the single source of truth for your project

### 2. Vocabulary Management
- Import SKOS vocabularies from a local RDF file — the serialization is auto-detected, covering everything rdflib supports (Turtle, JSON-LD, RDF/XML, N-Triples, N3, TriG, …) — or from CSV
- Or load directly from a remote URL — any RDF serialization rdflib supports is auto-detected
- Vocabularies are stored as tables directly in your GeoPackage
- Support for multiple vocabularies in the same GeoPackage
- Language support for German and English

### 3. Layer Binding
- Connect your vector data layers to vocabulary tables
- Bind multiple vocabularies to a single feature layer
- All binding information is stored in the GeoPackage configuration table

### 4. Semantic Annotation
- Browse vocabulary concepts in a tree structure
- Create annotation fields on your vector layers
- Use Value Relation widgets for easy concept selection
- Add semantic labels to your geographic features

### 5. Rule-Based Symbology
- Generate hierarchical symbology from your annotations
- Visualize data based on semantic concepts
- Automatically include all bound vocabularies

### 6. Linked Open Data (LOD) Export
- Export annotated feature data as Turtle (`.ttl`) Linked Open Data
- Enter your institution's object namespace, then set an Object ID, Label and CRM class for each annotated layer
- Annotation columns map to `oa:motivatedBy`, selected concept values map to `oa:hasTarget`
- Includes CIDOC-CRM, CRMdig (`crmdig:D9_Data_Object`), and GeoSPARQL geometry triples
- "Export All Layers to Turtle" merges everything into one file; layers sharing the same Object ID are aggregated into the same object automatically


## How to Use

### Prerequisites
- **Layers must be loaded in the project from a GeoPackage** before you can start annotation
- You need at least one vector layer with geographic features in a GeoPackage
- You need a SKOS vocabulary in RDF or CSV format

### Step-by-Step Usage

#### 1. Select Your GeoPackage
- Open the QSKOS plugin dock widget
- Go to the "GeoPackage" tab
- Click "Select GeoPackage" and choose your `.gpkg` file
- **This is mandatory** - all other functions depend on having an active GeoPackage

#### 2. Import Vocabularies
- Go to the "Vocabulary" tab
- Select your source type (Local RDF File, CSV, or Remote URL)
- Choose the language (German or English)
- Select your vocabulary file, or paste a URL to fetch from
- Click "Load into GeoPackage"
- The vocabulary will be stored as a table in your GeoPackage

#### 3. Bind Layers to Vocabularies
- Go to the "Layer" tab
- Select your feature layer from the dropdown (only shows layers from your GeoPackage)
- View available vocabularies in the "Bound Vocabularies" list
- Click "Bind Vocabulary" to connect your layer to a vocabulary
- You can bind multiple vocabularies to the same layer

#### 4. Annotate Your Features
- In the "Layer" tab, select a vocabulary from your bound vocabularies list
- Browse the concept hierarchy tree
- Check the concepts you want to use for annotation
- Annotation fields will be automatically created on your vector layer
- Open your layer's attribute table to add semantic annotations

#### 5. Generate Symbology (Optional)
- Go to the "Symbology" tab
- Click "Generate Rules from Annotations"
- The plugin will create hierarchical rule-based symbology
- Your features will be visualized based on their semantic annotations

#### 6. Export as Linked Open Data (LOD)
- Go to the "LOD Export" tab and enter your institution's **Object Namespace** (e.g. `https://museum.example.org/objects/`)
- One form is shown per annotated feature layer — for each, enter the Object ID (e.g. `O.34736`), Object Label (e.g. `Lederschuh`) and CRM class
- The CRM class is an editable dropdown (e.g. `crm:E22_Human_Made_Object`); type any class if the list doesn't fit
- Use "Export This Layer…" for a single layer, or "Export All Layers to Turtle" for everything
- Layers with the same Object ID are merged into one object in the output file


## Important Notes

- **GeoPackage requirement**: All layers must be loaded from a GeoPackage file for the plugin to work properly
- **Single source of truth**: All plugin data is stored in the GeoPackage, not in the QGIS project file
- **Portability**: You can move your GeoPackage file and all annotations will be preserved
- **No automatic deletion**: Unbinding vocabularies or unchecking concepts does NOT delete annotation fields - you must remove them manually if needed
- **Vocabulary formats**: Supported formats include any RDF serialization rdflib handles (Turtle, JSON-LD, RDF/XML, N-Triples, N3, TriG, …) — auto-detected for both local files and remote URLs — plus CSV with the specific structure below. JSON-LD vocabularies that model their hierarchy as nested `skos:narrower` are automatically inverted into the plugin's `broader`-based hierarchy.

### CSV Format Requirements

For CSV files to be imported as vocabularies, they must follow this column structure:

| Column Name | Description | Example |
|-------------|-------------|---------|
| `concept` | URI of the concept | `http://example.org/concept1` |
| `prefLabel` | Preferred labels with language tags (pipe-separated for multiple languages) | `Label@de|Label@en` |
| `definition` | Definitions with language tags (same format as prefLabel) | `Definition@de|Definition@en` |
| `broader` | Parent concept URI (empty for root concepts) | `http://example.org/parent` |
| `inScheme` | URI of the concept scheme (optional) | `http://example.org/scheme` |

**Language Tagging**: Use `@de` for German and `@en` for English labels. Multiple languages can be separated with pipes: `Label@de|Label@en`

## Benefits

- **Standardized annotation**: Use controlled vocabularies for consistent data labeling
- **Improved data quality**: Add semantic meaning to your geographic features
- **Better interoperability**: Enable data sharing and integration with other systems
- **Enhanced discovery**: Make your data more findable and understandable
- **Portable projects**: All data is contained in the GeoPackage file
- **Project independence**: Work with the same data across different QGIS projects

## Technical Details

The QSKOS plugin uses a dedicated configuration table (`qskos_layer_config`) inside your GeoPackage to track:
- Vocabulary registrations
- Layer bindings
- Language settings

All vocabulary tables are stored directly in the GeoPackage as attribute tables, making your data completely self-contained and portable.

The QSKOS plugin bridges the gap between geographic data and semantic web technologies, enabling richer, more meaningful spatial data management while maintaining data portability and project independence.