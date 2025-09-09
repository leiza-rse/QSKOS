# __init__.py
# qskos QGIS Plugin - Main Interface
# Generated based on specification: Updated QGIS Plugin Specification.docx

from PyQt5.QtWidgets import QAction, QMessageBox, QDockWidget, QVBoxLayout, QWidget, QTabWidget
from PyQt5.QtCore import Qt
from qgis.core import QgsProject, QgsVectorLayer, QgsField, QgsEditorWidgetSetup, QgsMapLayer
from qgis.gui import QgsMapLayerComboBox
from qgis.core import QgsMapLayerProxyModel
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
        
        # Vocabulary Tab
        self.vocab_tab = QWidget()
        self.setup_vocab_tab()
        
        # Layer Tab
        self.layer_tab = QWidget()
        self.setup_layer_tab()
        
        self.tab_widget.addTab(self.vocab_tab, "Vocabulary")
        self.tab_widget.addTab(self.layer_tab, "Layer")
        
        self.dock_widget.setWidget(self.tab_widget)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)
        self.dock_widget.hide()

        # Connect layer change signals for auto-refresh
        QgsProject.instance().layerWasAdded.connect(self.refresh_layer_combos)
        QgsProject.instance().layerWillBeRemoved.connect(self.refresh_layer_combos)

    def setup_vocab_tab(self):
        """Setup the Vocabulary tab UI (stub for now)."""
        layout = QVBoxLayout()
        layout.addWidget(QMessageBox.information(None, "Vocab Tab", "Vocabulary loading UI goes here."))
        self.vocab_tab.setLayout(layout)

    def setup_layer_tab(self):
        """Setup the Layer Binding and Tree View tab UI."""
        layout = QVBoxLayout()
        
        # Feature Layer Dropdown
        self.feature_layer_combo = QgsMapLayerComboBox()
        self.feature_layer_combo.setFilters(QgsMapLayerProxyModel.VectorLayer)
        layout.addWidget(self.feature_layer_combo)
        
        # Vocabulary Layer Dropdown
        self.vocab_layer_combo = QgsMapLayerComboBox()
        # We will filter this manually to show only qskos vocab layers
        layout.addWidget(self.vocab_layer_combo)
        
        # Bind Button
        from PyQt5.QtWidgets import QPushButton
        self.bind_button = QPushButton("Bind Layer to Vocabulary")
        self.bind_button.clicked.connect(self.bind_layers)
        layout.addWidget(self.bind_button)
        
        # Tree View Placeholder (actual tree view implementation would go here)
        from PyQt5.QtWidgets import QTreeWidget, QTreeWidgetItem
        self.tree_view = QTreeWidget()
        self.tree_view.setHeaderLabel("Concept Hierarchy")
        self.tree_view.itemChanged.connect(self.on_tree_item_changed)
        layout.addWidget(self.tree_view)
        
        self.layer_tab.setLayout(layout)
        self.refresh_layer_combos()

    def refresh_layer_combos(self):
        """Refresh dropdowns to show only valid layers."""
        # Refresh feature layers: only vector layers with geometry
        self.feature_layer_combo.setLayer(None)
        self.feature_layer_combo.setFilters(QgsMapLayerProxyModel.VectorLayer)
        
        # Refresh vocab layers: only delimited text layers with qskos:scheme property
        self.vocab_layer_combo.setLayer(None)
        self.vocab_layer_combo.setAllowEmptyLayer(True)
        self.vocab_layer_combo.setFilters(QgsMapLayerProxyModel.All)

        # Manually filter vocab layers
        vocab_layers = []
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsMapLayer.VectorLayer:
                if layer.customProperty("qskos:scheme"):
                    vocab_layers.append(layer)
        
        # We clear and re-add items since QgsMapLayerComboBox doesn't support custom filtering easily
        self.vocab_layer_combo.clear()
        self.vocab_layer_combo.addItem("", None)  # Empty item
        for layer in vocab_layers:
            self.vocab_layer_combo.addItem(layer.name(), layer.id())

    def bind_layers(self):
        """Bind the selected feature layer to the selected vocabulary layer."""
        feature_layer = self.feature_layer_combo.currentLayer()
        vocab_layer_id = self.vocab_layer_combo.currentData()
        vocab_layer = QgsProject.instance().mapLayer(vocab_layer_id)

        if not feature_layer or not vocab_layer:
            QMessageBox.warning(None, "Binding Error", "Please select both a feature layer and a vocabulary layer.")
            return

        scheme_uri = vocab_layer.customProperty("qskos:scheme")
        if not scheme_uri:
            QMessageBox.warning(None, "Binding Error", "Selected vocabulary layer is not a valid qskos vocabulary.")
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

    def toggle_dock_widget(self):
        """Show or hide the dock widget."""
        if self.dock_widget.isVisible():
            self.dock_widget.hide()
        else:
            self.dock_widget.show()

    def unload(self):
        """Remove the plugin UI elements."""
        self.iface.removeToolBarIcon(self.action)
        if self.dock_widget:
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget.deleteLater()
        del self.action

    def run(self):
        """Legacy run method - now toggles dock widget."""
        self.toggle_dock_widget()