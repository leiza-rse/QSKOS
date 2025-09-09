# __init__.py
# qskos QGIS Plugin - Main Interface
# Generated based on specification: Updated QGIS Plugin Specification.docx

from PyQt5.QtWidgets import (
    QAction, QMessageBox, QDockWidget, QVBoxLayout, QWidget, QTabWidget,
    QPushButton, QTreeWidget, QFormLayout, QLineEdit, QComboBox, QFileDialog,
    QLabel, QInputDialog, QTreeWidgetItem
)
from PyQt5.QtCore import Qt, QTimer
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsField, QgsEditorWidgetSetup, QgsMapLayer,
    QgsMapLayerProxyModel, QgsFeatureRequest
)
from qgis.gui import QgsMapLayerComboBox
import os
import sys

# Import utility functions from separate module
from .qskos_utils import (
    load_skos_source,
    convert_to_delimited_text_layer,
    build_concept_tree_from_layer,
    get_descendant_uris
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

        self.tab_widget.addTab(self.vocab_tab, "Vocabulary")
        self.tab_widget.addTab(self.layer_tab, "Layer")

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
            # Load concepts
            concepts = load_skos_source(source_text, source_type)

            if not concepts:
                raise ValueError("No concepts loaded from source.")

            # Extract or prompt for scheme URI
            scheme_uri = self.extract_or_prompt_scheme_uri(concepts, source_text)
            if not scheme_uri:
                return  # User canceled

            # Convert to layer
            vocab_layer = convert_to_delimited_text_layer(concepts, scheme_uri)

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

        root_items = build_concept_tree_from_layer(vocab_layer)
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
        """Create a new Map-type field with ValueRelation widget configured for descendants."""
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

        # Get descendant URIs for filtering
        descendant_uris = get_descendant_uris(self.current_vocab_layer, concept_uri)
        filter_expression = f'"skos:Concept" IN ({",".join([f"\'{uri}\'" for uri in descendant_uris])})'

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


# REQUIRED ENTRY POINT FOR QGIS
def classFactory(iface):
    return qskos(iface)