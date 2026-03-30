# layer.py
# qskos QGIS Plugin - Layer Tab Logic
# Handles layer binding, tree views, field management

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QPushButton, QTreeWidget, 
    QTreeWidgetItem
)
from PyQt5.QtCore import Qt, QTimer, QVariant
from qgis.core import QgsProject, QgsMapLayer, QgsField, QgsFeatureRequest, QgsEditorWidgetSetup, QgsDefaultValue, QgsMapLayerProxyModel
from qgis.gui import QgsMapLayerComboBox
from PyQt5.QtWidgets import QMessageBox
import os

# Import utility functions from separate module
from .hierarchy import (
    build_concept_tree_from_layer,
    build_hierarchy_index,
    get_descendant_uris_fast,
    get_filtered_descendant_uris_fast
)

from .fields import parse_field_value


class LayerManager:
    def __init__(self, plugin_instance):
        self.plugin = plugin_instance
        self.feature_layer_combo = None
        self.vocab_layer_combo = None
        self.tree_view = None
        self.bind_button = None
        
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
        self.feature_layer_combo.layerChanged.connect(self.plugin.on_feature_layer_changed)
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
        self.tree_view.itemChanged.connect(self.plugin.on_tree_item_changed)
        layout.addWidget(self.tree_view)

        layer_tab = QWidget()
        layer_tab.setLayout(layout)
        return layer_tab

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
        self.plugin.load_concept_tree(feature_layer, vocab_layer)

    def load_concept_tree(self, feature_layer, vocab_layer):
        """Load and display the SKOS concept hierarchy in the tree view."""
        if self.tree_view:
            self.tree_view.clear()
        self.plugin.current_feature_layer = feature_layer
        self.plugin.current_vocab_layer = vocab_layer

        # 👇 PRE-WARM HIERARCHY CACHE
        self.plugin.get_hierarchy_for_layer(vocab_layer)

        root_items = build_concept_tree_from_layer(vocab_layer, self.plugin.selected_language)
        if self.tree_view:
            for item in root_items:
                self.tree_view.addTopLevelItem(item)

        # Restore checked state from existing fields
        existing_fields = [field.name() for field in feature_layer.fields()]
        if self.tree_view:
            self.restore_checked_concepts(self.tree_view.invisibleRootItem(), existing_fields)

    def restore_checked_concepts(self, parent_item, existing_uris):
        """Recursively check tree items if their URI matches an existing field."""
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            concept_uri = child.data(0, Qt.UserRole)
            if concept_uri in existing_uris:
                child.setCheckState(0, Qt.Checked)
            self.restore_checked_concepts(child, existing_uris)

    def on_feature_layer_changed(self, layer):
        """Called when feature layer selection changes."""
        if not layer:
            if self.tree_view:
                self.tree_view.clear()
            self.plugin.current_feature_layer = None
            self.plugin.current_vocab_layer = None
            return

        # Check if this layer is bound to a vocabulary
        scheme_uri = layer.customProperty("qskos:binding")
        if not scheme_uri:
            if self.tree_view:
                self.tree_view.clear()
            self.plugin.current_feature_layer = layer
            self.plugin.current_vocab_layer = None
            return

        # Find vocab layer by scheme URI
        vocab_layer = self.plugin.find_vocab_layer_by_scheme(scheme_uri)
        if vocab_layer:
            # 👇 PRE-WARM CACHE ON LAYER SELECTION — ensures fast tree & future symbology
            self.plugin.get_hierarchy_for_layer(vocab_layer)
            self.load_concept_tree(layer, vocab_layer)
        else:
            if self.tree_view:
                self.tree_view.clear()
            QMessageBox.warning(None, "Binding Broken", 
                f"Vocabulary for scheme '{scheme_uri}' not found. Please re-bind.")
            self.plugin.current_feature_layer = layer
            self.plugin.current_vocab_layer = None

    def find_vocab_layer_by_scheme(self, scheme_uri):
        """Find a vocabulary layer by its qskos:scheme custom property."""
        for layer in QgsProject.instance().mapLayers().values():
            if (layer.type() == QgsMapLayer.VectorLayer and 
                layer.customProperty("qskos:scheme") == scheme_uri):
                return layer
        return None

    def create_annotation_field(self, concept_uri, label):
        """Create a new Map-type field with ValueRelation widget configured for descendants (excluding self)."""
        if not self.plugin.current_feature_layer or not self.plugin.current_vocab_layer:
            return

        # Check if field already exists
        if self.plugin.current_feature_layer.fields().lookupField(concept_uri) != -1:
            return  # Already exists

        # Add new field
        self.plugin.current_feature_layer.startEditing()
        new_field = QgsField(concept_uri, QVariant.Map)  # Explicitly use QVariant.Map
        self.plugin.current_feature_layer.addAttribute(new_field)
        self.plugin.current_feature_layer.updateFields()

        field_index = self.plugin.current_feature_layer.fields().lookupField(concept_uri)

        # 👇 SET DEFAULT VALUE TO EMPTY ARRAY
        default_clause = QgsDefaultValue("array()", True)
        self.plugin.current_feature_layer.setDefaultValueDefinition(field_index, default_clause)

        # Configure ValueRelation widget
        children_map, _ = self.plugin.get_hierarchy_for_layer(self.plugin.current_vocab_layer)
        target_uris = get_filtered_descendant_uris_fast(children_map, concept_uri)

        if not target_uris:
            filter_expression = "0"  # No matches
        else:
            quoted_uris = ["'" + uri.replace("'", "''") + "'" for uri in target_uris]
            filter_expression = f'"concept" IN ({",".join(quoted_uris)})'

        config = {
            'Layer': self.plugin.current_vocab_layer.id(),
            'Key': 'concept',
            'Value': 'prefLabel',
            'Description': 'definition',
            'FilterExpression': filter_expression,
            'AllowMulti': True,
            'UseCompleter': True,
            'OrderByValue': True
        }

        widget_setup = QgsEditorWidgetSetup('ValueRelation', config)
        self.plugin.current_feature_layer.setEditorWidgetSetup(field_index, widget_setup)
        self.plugin.current_feature_layer.setFieldAlias(field_index, label)

        self.plugin.current_feature_layer.commitChanges()
        QMessageBox.information(None, "Field Created", f"Annotation field '{label}' created successfully.")

    def remove_annotation_field(self, concept_uri):
        """Remove the annotation field (optional: confirm with user)."""
        if not self.plugin.current_feature_layer:
            return

        field_index = self.plugin.current_feature_layer.fields().lookupField(concept_uri)
        if field_index == -1:
            return

        reply = QMessageBox.question(None, 'Confirm Delete',
                                     f"Are you sure you want to delete the field for '{concept_uri}'?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.plugin.current_feature_layer.startEditing()
            self.plugin.current_feature_layer.deleteAttribute(field_index)
            self.plugin.current_feature_layer.updateFields()
            self.plugin.current_feature_layer.commitChanges()
            QMessageBox.information(None, "Field Deleted", "Annotation field removed.")

    def refresh_layer_combos(self):
        """Safely refresh dropdowns to show only valid layers."""
        try:
            # If dock widget is gone or not visible, skip refresh
            if not self.plugin.dock_widget or not self.plugin.dock_widget.isVisible():
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
        if self.plugin.dock_widget:  # Only if plugin UI still exists
            QTimer.singleShot(0, self.refresh_layer_combos)