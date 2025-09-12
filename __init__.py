# __init__.py
# qskos QGIS Plugin - Main Interface
# Generated based on specification: Updated QGIS Plugin Specification.docx

from PyQt5.QtWidgets import (
    QAction, QMessageBox, QDockWidget, QVBoxLayout, QWidget, QTabWidget,
    QPushButton, QTreeWidget, QFormLayout, QLineEdit, QComboBox, QFileDialog,
    QLabel, QInputDialog, QTreeWidgetItem, QHBoxLayout
)
from PyQt5.QtCore import Qt, QTimer, QVariant
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsField, QgsEditorWidgetSetup, QgsMapLayer,
    QgsMapLayerProxyModel, QgsFeatureRequest, QgsRuleBasedRenderer, QgsSymbol, 
    QgsWkbTypes, QgsExpression, QgsSingleSymbolRenderer
)
from qgis.gui import QgsMapLayerComboBox, QgsRendererPropertiesDialog
from PyQt5.QtGui import QColor
import os
import sys
import random

# Import utility functions from separate module
from .qskos_utils import (
    load_skos_source,
    convert_to_delimited_text_layer,
    build_concept_tree_from_layer,
    get_descendant_uris,
    get_filtered_descendant_uris
)


class qskos:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.dock_widget = None
        self.vocab_layer_combo = None
        self.feature_layer_combo = None
        self.tree_view = None
        self.current_vocab_layer = None
        self.current_feature_layer = None
        self.selected_language = "en"  # Default language selection

    def initGui(self):
        """Initialize the plugin GUI: toolbar icon and dock widget."""
        self.action = QAction('qskos', self.iface.mainWindow())
        self.action.triggered.connect(self.toggle_dock_widget)
        self.iface.addToolBarIcon(self.action)

        # Create dock widget
        self.dock_widget = QDockWidget("qskos Semantic Annotation", self.iface.mainWindow())
        self.dock_widget.setObjectName("qskosDockWidget")

        # Main tab widget
        self.tab_widget = QTabWidget()

        # Vocabulary Tab — FULLY IMPLEMENTED
        self.vocab_tab = QWidget()
        self.setup_vocab_tab()

        # Layer Tab — FULLY IMPLEMENTED
        self.layer_tab = QWidget()
        self.setup_layer_tab()

        # Symbology Tab — UPDATED
        self.symbology_tab = QWidget()
        self.setup_symbology_tab()

        self.tab_widget.addTab(self.vocab_tab, "Vocabulary")
        self.tab_widget.addTab(self.layer_tab, "Layer")
        self.tab_widget.addTab(self.symbology_tab, "Symbology")

        self.dock_widget.setWidget(self.tab_widget)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)
        self.dock_widget.hide()

        # Connect layer change signals for auto-refresh
        project = QgsProject.instance()
        project.layerWasAdded.connect(self.schedule_refresh)
        project.layerWillBeRemoved.connect(self.schedule_refresh)

    def setup_vocab_tab(self):
        """Fully implemented Vocabulary Tab UI for loading SKOS sources."""
        layout = QFormLayout()

        # Source Type Selector
        self.source_type_combo = QComboBox()
        self.source_type_combo.addItems([
            "Local Turtle (.ttl)",
            "Local JSON-LD (.jsonld)",
            "Local CSV (.csv)",
            "Remote URL (Turtle/JSON-LD)"
        ])
        layout.addRow("Source Type:", self.source_type_combo)

        # Language Selector — NEW
        self.language_combo = QComboBox()
        self.language_combo.addItems(["en", "de"])
        self.language_combo.setCurrentText("en")
        self.language_combo.currentTextChanged.connect(self.on_language_changed)
        layout.addRow("Display Language:", self.language_combo)

        # Source Path/URL Input
        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("Enter file path or URL...")
        layout.addRow("Source:", self.source_input)

        # Browse Button (for local files)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.browse_skos_file)
        layout.addRow("", browse_button)

        # Load Button
        self.load_vocab_button = QPushButton("Load Vocabulary")
        self.load_vocab_button.clicked.connect(self.on_load_vocab_clicked)
        layout.addRow("", self.load_vocab_button)

        # Status Label
        self.vocab_status_label = QLabel("Ready to load vocabulary.")
        layout.addRow("", self.vocab_status_label)

        self.vocab_tab.setLayout(layout)

    def on_language_changed(self, lang):
        """Update selected language for display and storage."""
        self.selected_language = lang

    def setup_layer_tab(self):
        """Setup the Layer Binding and Tree View tab UI."""
        layout = QVBoxLayout()

        # Use form layout for labeled dropdowns
        form_layout = QFormLayout()

        # Feature Layer Dropdown — ONLY layers with geometry, EXCLUDE vocab layers
        self.feature_layer_combo = QgsMapLayerComboBox()
        self.feature_layer_combo.setFilters(QgsMapLayerProxyModel.VectorLayer | QgsMapLayerProxyModel.HasGeometry)
        self.feature_layer_combo.setAllowEmptyLayer(True)
        self.feature_layer_combo.setShowCrs(True)
        self.feature_layer_combo.layerChanged.connect(self.on_feature_layer_changed)
        form_layout.addRow("Feature Layer (Geometry):", self.feature_layer_combo)

        # Vocabulary Layer Dropdown — ONLY layers with qskos:scheme
        self.vocab_layer_combo = QgsMapLayerComboBox()
        self.vocab_layer_combo.setAllowEmptyLayer(True)
        form_layout.addRow("Vocabulary Layer (SKOS):", self.vocab_layer_combo)

        layout.addLayout(form_layout)

        # Bind Button
        self.bind_button = QPushButton("Bind Layer to Vocabulary")
        self.bind_button.clicked.connect(self.bind_layers)
        layout.addWidget(self.bind_button)

        # Tree View
        self.tree_view = QTreeWidget()
        self.tree_view.setHeaderLabel("Concept Hierarchy")
        self.tree_view.itemChanged.connect(self.on_tree_item_changed)
        layout.addWidget(self.tree_view)

        self.layer_tab.setLayout(layout)
        self.refresh_layer_combos()

    def browse_skos_file(self):
        """Open file dialog to select local SKOS file."""
        options = QFileDialog.Options()
        source_type = self.source_type_combo.currentIndex()

        if source_type == 0:  # TTL
            file_filter = "Turtle Files (*.ttl);;All Files (*)"
        elif source_type == 1:  # JSON-LD
            file_filter = "JSON-LD Files (*.jsonld);;All Files (*)"
        elif source_type == 2:  # CSV
            file_filter = "CSV Files (*.csv);;All Files (*)"
        else:  # URL — no file dialog
            return

        file_path, _ = QFileDialog.getOpenFileName(
            None, "Select SKOS File", "", file_filter, options=options
        )
        if file_path:
            self.source_input.setText(file_path)

    def on_load_vocab_clicked(self):
        """Load and convert SKOS vocabulary based on user input."""
        source_text = self.source_input.text().strip()
        if not source_text:
            QMessageBox.warning(None, "Input Required", "Please enter a file path or URL.")
            return

        source_type_index = self.source_type_combo.currentIndex()
        source_type_map = {
            0: 'ttl',
            1: 'jsonld',
            2: 'csv',
            3: 'url'
        }
        source_type = source_type_map[source_type_index]

        try:
            # Load concepts — pass selected language for filtering
            concepts = load_skos_source(source_text, source_type, self.selected_language)

            if not concepts:
                raise ValueError("No concepts loaded from source.")

            # Extract or prompt for scheme URI
            scheme_uri = self.extract_or_prompt_scheme_uri(concepts, source_text)
            if not scheme_uri:
                return  # User canceled

            # Convert to layer — store only selected language’s labels
            vocab_layer = convert_to_delimited_text_layer(concepts, scheme_uri, self.selected_language)

            # Success
            self.vocab_status_label.setText(f"✅ Loaded: {vocab_layer.name()}")
            QMessageBox.information(None, "Success", f"Vocabulary '{vocab_layer.name()}' loaded successfully.")

            # Refresh dropdowns to include new layer
            self.refresh_layer_combos()

        except Exception as e:
            self.vocab_status_label.setText("❌ Load failed.")
            QMessageBox.critical(None, "Load Error", f"Failed to load vocabulary:\n{str(e)}")
            import traceback
            traceback.print_exc()  # For debugging in QGIS log

    def extract_or_prompt_scheme_uri(self, concepts, source_hint=""):
        """Try to extract scheme URI from data, or prompt user."""
        # Try to get from first concept's inScheme
        for c in concepts:
            if c.get('skos:inScheme'):
                return c['skos:inScheme']

        # Fallback: use source as scheme (for CSV or URL)
        default_scheme = source_hint if source_hint else "http://example.org/scheme/unknown"

        scheme_uri, ok = QInputDialog.getText(
            None,
            "Enter Concept Scheme URI",
            "No skos:inScheme found. Please enter the Concept Scheme URI:",
            text=default_scheme
        )
        return scheme_uri if ok else None

    def refresh_layer_combos(self):
        """Safely refresh dropdowns to show only valid layers."""
        try:
            # If dock widget is gone or not visible, skip refresh
            if not self.dock_widget or not self.dock_widget.isVisible():
                return

            all_layers = list(QgsProject.instance().mapLayers().values())
            
            # Identify vocabulary layers by custom property
            vocab_layer_ids = {
                layer.id() for layer in all_layers
                if layer.type() == QgsMapLayer.VectorLayer and layer.customProperty("qskos:scheme")
            }
            
            # Refresh Feature Layer Combo
            if self.feature_layer_combo:
                self.feature_layer_combo.setLayer(None)
                self.feature_layer_combo.setFilters(QgsMapLayerProxyModel.VectorLayer | QgsMapLayerProxyModel.HasGeometry)
                feature_excepted_layers = [
                    layer for layer in all_layers
                    if layer.id() in vocab_layer_ids
                ]
                self.feature_layer_combo.setExceptedLayerList(feature_excepted_layers)

            # Refresh Vocab Layer Combo
            if self.vocab_layer_combo:
                excepted_vocab_layers = [
                    layer for layer in all_layers
                    if layer.id() not in vocab_layer_ids
                ]
                self.vocab_layer_combo.setExceptedLayerList(excepted_vocab_layers)
                self.vocab_layer_combo.setAllowEmptyLayer(True)

        except RuntimeError:
            # Widget was deleted — safe to ignore
            pass
        except Exception as e:
            # Log unexpected errors (optional)
            print(f"Error in refresh_layer_combos: {e}")

    def schedule_refresh(self):
        """Schedule a safe refresh of layer combos."""
        if self.dock_widget:  # Only if plugin UI still exists
            QTimer.singleShot(0, self.refresh_layer_combos)

    def bind_layers(self):
        """Bind the selected feature layer to the selected vocabulary layer."""
        feature_layer = self.feature_layer_combo.currentLayer()
        vocab_layer = self.vocab_layer_combo.currentLayer()

        if not feature_layer:
            QMessageBox.warning(None, "Binding Error", "Please select a valid feature layer with geometry.")
            return

        if not vocab_layer:
            QMessageBox.warning(None, "Binding Error", "Please select a valid vocabulary layer.")
            return

        # Extra safety: ensure feature layer is NOT a vocabulary layer
        if feature_layer.customProperty("qskos:scheme"):
            QMessageBox.warning(None, "Binding Error", "Cannot bind a vocabulary layer as a feature layer.")
            return

        scheme_uri = vocab_layer.customProperty("qskos:scheme")
        if not scheme_uri:
            QMessageBox.warning(None, "Binding Error", "Selected vocabulary layer is not a valid qskos vocabulary (missing qskos:scheme).")
            return

        # Set binding property on feature layer
        feature_layer.setCustomProperty("qskos:binding", scheme_uri)
        QMessageBox.information(None, "Success", f"Layer '{feature_layer.name()}' bound to vocabulary '{vocab_layer.name()}'.")

        # Load and display concept tree
        self.load_concept_tree(feature_layer, vocab_layer)

    def load_concept_tree(self, feature_layer, vocab_layer):
        """Load and display the SKOS concept hierarchy in the tree view."""
        self.tree_view.clear()
        self.current_feature_layer = feature_layer
        self.current_vocab_layer = vocab_layer

        root_items = build_concept_tree_from_layer(vocab_layer, self.selected_language)
        for item in root_items:
            self.tree_view.addTopLevelItem(item)

        # Restore checked state from existing fields
        existing_fields = [field.name() for field in feature_layer.fields()]
        self.restore_checked_concepts(self.tree_view.invisibleRootItem(), existing_fields)

    def restore_checked_concepts(self, parent_item, existing_uris):
        """Recursively check tree items if their URI matches an existing field."""
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            concept_uri = child.data(0, Qt.UserRole)
            if concept_uri in existing_uris:
                child.setCheckState(0, Qt.Checked)
            self.restore_checked_concepts(child, existing_uris)

    def on_tree_item_changed(self, item, column):
        """Handle checkbox state change: create or remove annotation field."""
        if column != 0:
            return

        concept_uri = item.data(0, Qt.UserRole)
        label = item.text(0)
        state = item.checkState(0)

        if state == Qt.Checked:
            self.create_annotation_field(concept_uri, label)
        elif state == Qt.Unchecked:
            self.remove_annotation_field(concept_uri)

    def create_annotation_field(self, concept_uri, label):
        """Create a new Map-type field with ValueRelation widget configured for siblings and descendants (excluding self)."""
        if not self.current_feature_layer or not self.current_vocab_layer:
            return

        # Check if field already exists
        if self.current_feature_layer.fields().lookupField(concept_uri) != -1:
            return  # Already exists

        # Add new field
        self.current_feature_layer.startEditing()
        new_field = QgsField(concept_uri, 10)  # QVariant.Map = 10
        self.current_feature_layer.addAttribute(new_field)
        self.current_feature_layer.updateFields()

        # Configure ValueRelation widget
        field_index = self.current_feature_layer.fields().lookupField(concept_uri)

        # Get sibling and descendant URIs for filtering — EXCLUDE self
        target_uris = get_filtered_descendant_uris(self.current_vocab_layer, concept_uri)
        if not target_uris:
            filter_expression = "0"  # No matches
        else:
            quoted_uris = [f"'{uri}'" for uri in target_uris]
            filter_expression = f'"skos:Concept" IN ({",".join(quoted_uris)})'

        config = {
            'Layer': self.current_vocab_layer.id(),
            'Key': 'skos:Concept',
            'Value': 'skos:prefLabel',
            'Description': 'skos:definition',
            'FilterExpression': filter_expression,
            'AllowMulti': True,
            'UseCompleter': True,
            'OrderByValue': True
        }

        widget_setup = QgsEditorWidgetSetup('ValueRelation', config)
        self.current_feature_layer.setEditorWidgetSetup(field_index, widget_setup)
        self.current_feature_layer.setFieldAlias(field_index, label)

        self.current_feature_layer.commitChanges()
        QMessageBox.information(None, "Field Created", f"Annotation field '{label}' created successfully.")

    def remove_annotation_field(self, concept_uri):
        """Remove the annotation field (optional: confirm with user)."""
        if not self.current_feature_layer:
            return

        field_index = self.current_feature_layer.fields().lookupField(concept_uri)
        if field_index == -1:
            return

        reply = QMessageBox.question(None, 'Confirm Delete',
                                     f"Are you sure you want to delete the field for '{concept_uri}'?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.current_feature_layer.startEditing()
            self.current_feature_layer.deleteAttribute(field_index)
            self.current_feature_layer.updateFields()
            self.current_feature_layer.commitChanges()
            QMessageBox.information(None, "Field Deleted", "Annotation field removed.")

    def on_feature_layer_changed(self, layer):
        """Called when feature layer selection changes."""
        if not layer:
            self.tree_view.clear()
            self.current_feature_layer = None
            self.current_vocab_layer = None
            return

        # Check if this layer is bound to a vocabulary
        scheme_uri = layer.customProperty("qskos:binding")
        if not scheme_uri:
            self.tree_view.clear()
            self.current_feature_layer = layer
            self.current_vocab_layer = None
            return

        # Find vocab layer by scheme URI
        vocab_layer = self.find_vocab_layer_by_scheme(scheme_uri)
        if vocab_layer:
            self.load_concept_tree(layer, vocab_layer)
        else:
            self.tree_view.clear()
            QMessageBox.warning(None, "Binding Broken", 
                f"Vocabulary for scheme '{scheme_uri}' not found. Please re-bind.")
            self.current_feature_layer = layer
            self.current_vocab_layer = None

    def find_vocab_layer_by_scheme(self, scheme_uri):
        """Find a vocabulary layer by its qskos:scheme custom property."""
        for layer in QgsProject.instance().mapLayers().values():
            if (layer.type() == QgsMapLayer.VectorLayer and 
                layer.customProperty("qskos:scheme") == scheme_uri):
                return layer
        return None

    def toggle_dock_widget(self):
        """Show or hide the dock widget."""
        if self.dock_widget.isVisible():
            self.dock_widget.hide()
        else:
            self.dock_widget.show()
            # Optional: refresh comboboxes when dock is shown
            self.refresh_layer_combos()

    def unload(self):
        """Remove the plugin UI elements and disconnect signals."""
        # Disconnect layer signals
        project = QgsProject.instance()
        try:
            project.layerWasAdded.disconnect(self.schedule_refresh)
            project.layerWillBeRemoved.disconnect(self.schedule_refresh)
        except TypeError:
            # Signal was not connected or already disconnected
            pass

        # Remove toolbar icon
        self.iface.removeToolBarIcon(self.action)

        # Remove dock widget
        if self.dock_widget:
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget.deleteLater()
            self.dock_widget = None

        del self.action

    def run(self):
        """Legacy run method - now toggles dock widget."""
        self.toggle_dock_widget()

    # ================
    # SYMBOLOGY TAB
    # ================

    def setup_symbology_tab(self):
        """Setup the Symbology Tab UI."""
        layout = QVBoxLayout()

        info_label = QLabel("Generate hierarchical rule-based symbology grouped by annotation fields.")
        layout.addWidget(info_label)

        self.generate_symbology_button = QPushButton("Generate Rules from Annotations")
        self.generate_symbology_button.clicked.connect(self.generate_rule_based_symbology)
        layout.addWidget(self.generate_symbology_button)

        self.reset_symbology_button = QPushButton("Reset to Default Symbology")
        self.reset_symbology_button.clicked.connect(self.reset_symbology)
        layout.addWidget(self.reset_symbology_button)

        self.symbology_status_label = QLabel("Select a feature layer with annotation fields.")
        layout.addWidget(self.symbology_status_label)

        self.symbology_tab.setLayout(layout)

    def reset_symbology(self):
        """Reset layer symbology to default single symbol."""
        layer = self.current_feature_layer
        if not layer:
            QMessageBox.warning(None, "No Layer", "No feature layer selected.")
            return

        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        renderer = QgsSingleSymbolRenderer(symbol)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        self.iface.layerTreeView().refreshLayerSymbology(layer.id())
        QMessageBox.information(None, "Reset", "Symbology reset to default.")
        self.symbology_status_label.setText("✅ Symbology reset to default.")

    def get_checked_concept_uris(self):
        """Recursively get all checked concept URIs from the tree view."""
        if not self.tree_view:
            return []
        root = self.tree_view.invisibleRootItem()
        uris = []
        self._collect_checked_uris(root, uris)
        return uris

    def _collect_checked_uris(self, parent_item, uris):
        """Recursive helper to collect checked URIs."""
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.checkState(0) == Qt.Checked:
                uri = child.data(0, Qt.UserRole)
                uris.append(uri)
            self._collect_checked_uris(child, uris)

    def random_color(self):
        """Generate a random QColor."""
        return QColor(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))

    def parse_pg_array_literal(self, s):
        """
        Parse PostgreSQL-style array literal: '{"a","b","c"}'
        Returns list of strings.
        """
        if not isinstance(s, str) or not s.startswith('{') or not s.endswith('}'):
            return []
        # Strip braces
        inner = s[1:-1]
        if not inner:
            return []
        # Split by unquoted commas — QGIS escapes inner quotes as ""
        parts = inner.split(',')
        result = []
        for part in parts:
            part = part.strip()
            if part.startswith('"') and part.endswith('"'):
                part = part[1:-1]  # Remove surrounding quotes
                part = part.replace('""', '"')  # Unescape doubled quotes
            result.append(part)
        return result

    def generate_rule_based_symbology(self):
        """Generate hierarchical rule-based symbology grouped by field (root concept)."""
        layer = self.current_feature_layer
        vocab_layer = self.current_vocab_layer

        if not layer:
            QMessageBox.warning(None, "No Layer", "Please select a feature layer first.")
            return

        if not vocab_layer:
            QMessageBox.warning(None, "No Vocabulary", "Layer is not bound to a vocabulary.")
            return

        # Get all checked root concepts → these are our field groups
        checked_uris = self.get_checked_concept_uris()
        if not checked_uris:
            QMessageBox.warning(None, "No Annotations", "No checked vocabulary concepts found. Please check some in the Layer tab.")
            return

        # Build mapping: URI → prefLabel + broader
        uri_to_label = {}
        uri_to_broader = {}
        for feat in vocab_layer.getFeatures():
            uri = feat['skos:Concept']
            label = feat['skos:prefLabel']
            broader = feat['skos:broader'] or None
            uri_to_label[uri] = label
            uri_to_broader[uri] = broader

        # Build root → descendants map for each field
        field_to_descendants = {}
        for field_uri in checked_uris:
            descendants = set(get_descendant_uris(vocab_layer, field_uri))
            field_to_descendants[field_uri] = descendants

        # Root rule for renderer
        root_rule = QgsRuleBasedRenderer.Rule(None)

        for field_uri in checked_uris:
            field_label = uri_to_label.get(field_uri, field_uri)
            field_index = layer.fields().lookupField(field_uri)
            if field_index == -1:
                continue

            # Get all URIs used in this field across all features
            directly_annotated_uris = set()
            valid_descendants = field_to_descendants[field_uri]

            for feat in layer.getFeatures():
                val = feat[field_uri]
                uri_list = []

                # Handle NULL QVariant
                if isinstance(val, QVariant) and val.isNull():
                    val = None

                if val is None or val == '':
                    pass
                elif isinstance(val, list):
                    uri_list = [str(v).strip() for v in val if isinstance(v, str) and str(v).strip()]
                elif isinstance(val, str):
                    # PostgreSQL array literal: '{"a","b"}'
                    if val.startswith('{') and val.endswith('}'):
                        uri_list = self.parse_pg_array_literal(val)
                        uri_list = [u for u in uri_list if u]
                    # Pipe-separated (QGIS default for shapefiles, etc.)
                    elif '|' in val:
                        parts = [p.strip() for p in val.split('|')]
                        uri_list = [p for p in parts if p]
                    # JSON array (rare)
                    elif val.startswith('[') and val.endswith(']'):
                        try:
                            import json
                            parsed = json.loads(val)
                            if isinstance(parsed, list):
                                uri_list = [str(v).strip() for v in parsed if isinstance(v, str) and str(v).strip()]
                        except:
                            pass
                    # Single URI
                    else:
                        stripped = val.strip()
                        if stripped:
                            uri_list = [stripped]

                for uri in uri_list:
                    if uri in valid_descendants:
                        directly_annotated_uris.add(uri)

            # Helper to get ancestors up to field root
            def get_ancestors(uri):
                ancestors = []
                visited = set()
                current = uri
                while current and current != field_uri and current not in visited:
                    visited.add(current)
                    parent = uri_to_broader.get(current)
                    if not parent or parent == current:
                        break
                    ancestors.append(parent)
                    if parent == field_uri:
                        break
                    current = parent
                return ancestors

            # Collect all concepts to visualize (annotated + ancestors)
            concepts_to_visualize = set()
            for uri in directly_annotated_uris:
                concepts_to_visualize.add(uri)
                ancestors = get_ancestors(uri)
                for anc in ancestors:
                    if anc in field_to_descendants[field_uri]:
                        concepts_to_visualize.add(anc)

            # Skip if nothing to visualize
            if not concepts_to_visualize:
                continue

            # --- ✅ KEY CHANGE: Make GROUP RULE itself the ROOT RULE ---
            # Get all descendant URIs — EXCLUDE root (since it's not annotatable)
            all_descendant_uris = get_filtered_descendant_uris(vocab_layer, field_uri)

            if not all_descendant_uris:
                continue  # No descendants? Skip.

            # Build OR expression using LIKE for descendant URIs only
            or_clauses_root = []
            for u in all_descendant_uris:
                safe_u = u.replace("'", "''")
                or_clauses_root.append(f"\"{field_uri}\" LIKE '%{safe_u}%'")
            expr_str_root = " OR ".join(or_clauses_root) if or_clauses_root else "0"

            # Create symbol for group rule
            group_symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            group_symbol.setColor(self.random_color())

            # Create group rule WITH SYMBOL AND FILTER — it becomes a selectable rule!
            group_rule = QgsRuleBasedRenderer.Rule(
                symbol=group_symbol.clone(),
                filterExp=expr_str_root,
                label=field_label,
                description='All descendants (root not annotatable)'
            )
            group_rule.setActive(True)

            # --- Add CHILD RULES for DESCENDANTS ONLY (excluding root) ---
            for uri in concepts_to_visualize:
                if uri == field_uri:
                    continue  # Skip root — not annotatable

                label = uri_to_label.get(uri, uri)
                desc_uris = get_descendant_uris(vocab_layer, uri)
                if not desc_uris:
                    continue

                # Build OR expression using LIKE
                or_clauses = []
                for u in desc_uris:
                    safe_u = u.replace("'", "''")
                    or_clauses.append(f"\"{field_uri}\" LIKE '%{safe_u}%'")
                expr_str = " OR ".join(or_clauses) if or_clauses else "0"

                symbol = QgsSymbol.defaultSymbol(layer.geometryType())
                symbol.setColor(self.random_color())

                child_rule = QgsRuleBasedRenderer.Rule(
                    symbol=symbol.clone(),
                    filterExp=expr_str,
                    label=label,
                    description=''
                )
                child_rule.setActive(True)
                group_rule.appendChild(child_rule)

            # Add ELSE rule for unannotated features in this field
            else_symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            else_symbol.setColor(QColor(200, 200, 200))  # Light gray
            else_rule = QgsRuleBasedRenderer.Rule(
                symbol=else_symbol,
                filterExp='',
                label='(Unannotated)',
                description='',
                elseRule=True
            )
            else_rule.setActive(True)
            group_rule.appendChild(else_rule)

            root_rule.appendChild(group_rule)

        if root_rule.children():
            renderer = QgsRuleBasedRenderer(root_rule)
            layer.setRenderer(renderer)
            layer.triggerRepaint()
            self.iface.layerTreeView().refreshLayerSymbology(layer.id())
            QMessageBox.information(None, "Success", f"Generated hierarchical symbology for {len(checked_uris)} fields.")
            self.symbology_status_label.setText(f"✅ Generated symbology for {len(checked_uris)} fields.")
        else:
            QMessageBox.information(None, "No Data", "No annotation values found to generate symbology.")


# REQUIRED ENTRY POINT FOR QGIS
def classFactory(iface):
    return qskos(iface)