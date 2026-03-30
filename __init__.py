# __init__.py
# qskos QGIS Plugin - Main Interface
# Generated based on specification: Updated QGIS Plugin Specification.docx

from PyQt5.QtWidgets import (
    QAction, QMessageBox, QDockWidget, QVBoxLayout, QWidget, QTabWidget,
    QPushButton, QTreeWidget, QFormLayout, QLineEdit, QComboBox, QFileDialog,
    QLabel, QInputDialog, QTreeWidgetItem
)
from PyQt5.QtCore import Qt, QTimer, QVariant
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsField, QgsEditorWidgetSetup, QgsMapLayer,
    QgsMapLayerProxyModel, QgsFeatureRequest, QgsRuleBasedRenderer, QgsSymbol, 
    QgsWkbTypes, QgsExpression, QgsSingleSymbolRenderer, QgsDefaultValue
)
from qgis.gui import QgsMapLayerComboBox, QgsRendererPropertiesDialog
from PyQt5.QtGui import QColor
import os
import sys
import random

# Import module classes
from .vocabulary import VocabularyManager
from .layer import LayerManager
from .symbology import SymbologyManager

# Import utility functions from separate modules
from .hierarchy import (
    build_concept_tree_from_layer,
    build_hierarchy_index,
    get_descendant_uris_fast,
    get_filtered_descendant_uris_fast
)

from .fields import parse_field_value

from .skos import (
    load_skos_source,
    convert_to_delimited_text_layer
)

class qskos:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.dock_widget = None
        self.current_vocab_layer = None
        self.current_feature_layer = None
        self.selected_language = "en"  # Default language selection
        self.hierarchy_cache = {}      # vocab_layer.id() → (children_map, concept_labels)
        
        # Initialize managers
        self.vocabulary_manager = VocabularyManager(self)
        self.layer_manager = LayerManager(self)
        self.symbology_manager = SymbologyManager(self)

    def get_hierarchy_for_layer(self, vocab_layer):
        """
        Returns (children_map, concept_labels) for vocab_layer.
        Builds and caches it if not already present.
        Safe for saved/reopened projects — layer.id() changes → auto-rebuild.
        """
        layer_id = vocab_layer.id()
        if layer_id not in self.hierarchy_cache:
            children_map, concept_labels = build_hierarchy_index(vocab_layer)
            self.hierarchy_cache[layer_id] = (children_map, concept_labels)
            print(f"✅ Built hierarchy cache for vocab layer: {vocab_layer.name()}")

        return self.hierarchy_cache[layer_id]

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
        self.vocab_tab = self.vocabulary_manager.setup_vocab_tab()

        # Layer Tab — FULLY IMPLEMENTED
        self.layer_tab = self.layer_manager.setup_layer_tab()

        # Symbology Tab — UPDATED
        self.symbology_tab = self.symbology_manager.setup_symbology_tab()

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

    def toggle_dock_widget(self):
        """Show or hide the dock widget."""
        if self.dock_widget:
            if self.dock_widget.isVisible():
                self.dock_widget.hide()
            else:
                self.dock_widget.show()
                # Optional: refresh comboboxes when dock is shown
                self.layer_manager.refresh_layer_combos()

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
        if hasattr(self, 'action'):
            self.iface.removeToolBarIcon(self.action)

        # Remove dock widget
        if self.dock_widget:
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget.deleteLater()
            self.dock_widget = None

    def run(self):
        """Legacy run method - now toggles dock widget."""
        self.toggle_dock_widget()

    def schedule_refresh(self):
        """Schedule a safe refresh of layer combos."""
        if self.dock_widget:  # Only if plugin UI still exists
            QTimer.singleShot(0, self.layer_manager.refresh_layer_combos)

    def on_language_changed(self, lang):
        """Update selected language for display and storage."""
        self.selected_language = lang

    def browse_skos_file(self):
        """Open file dialog to select local SKOS file."""
        self.vocabulary_manager.browse_skos_file()

    def on_load_vocab_clicked(self):
        """Load and convert SKOS vocabulary based on user input."""
        self.vocabulary_manager.on_load_vocab_clicked()

    def extract_or_prompt_scheme_uri(self, concepts, source_hint=""):
        """Try to extract scheme URI from data, or prompt user."""
        return self.vocabulary_manager.extract_or_prompt_scheme_uri(concepts, source_hint)

    def refresh_layer_combos(self):
        """Safely refresh dropdowns to show only valid layers."""
        self.layer_manager.refresh_layer_combos()

    def bind_layers(self):
        """Bind the selected feature layer to the selected vocabulary layer."""
        self.layer_manager.bind_layers()

    def load_concept_tree(self, feature_layer, vocab_layer):
        """Load and display the SKOS concept hierarchy in the tree view."""
        self.layer_manager.load_concept_tree(feature_layer, vocab_layer)

    def restore_checked_concepts(self, parent_item, existing_uris):
        """Recursively check tree items if their URI matches an existing field."""
        self.layer_manager.restore_checked_concepts(parent_item, existing_uris)

    def on_tree_item_changed(self, item, column):
        """Handle checkbox state change: create or remove annotation field."""
        if column != 0:
            return

        concept_uri = item.data(0, Qt.UserRole)
        label = item.text(0)
        state = item.checkState(0)

        if state == Qt.Checked:
            self.layer_manager.create_annotation_field(concept_uri, label)
        elif state == Qt.Unchecked:
            self.layer_manager.remove_annotation_field(concept_uri)

    def on_feature_layer_changed(self, layer):
        """Called when feature layer selection changes."""
        self.layer_manager.on_feature_layer_changed(layer)

    def find_vocab_layer_by_scheme(self, scheme_uri):
        """Find a vocabulary layer by its qskos:scheme custom property."""
        return self.layer_manager.find_vocab_layer_by_scheme(scheme_uri)

    def reset_symbology(self):
        """Reset layer symbology to default single symbol."""
        self.symbology_manager.reset_symbology()

    def get_checked_concept_uris(self):
        """Recursively get all checked concept URIs from the tree view."""
        return self.symbology_manager.get_checked_concept_uris()

    def _collect_checked_uris(self, parent_item, uris):
        """Recursive helper to collect checked URIs."""
        self.symbology_manager._collect_checked_uris(parent_item, uris)

    def random_color(self):
        """Generate a random QColor."""
        return self.symbology_manager.random_color()

    def generate_rule_based_symbology(self):
        """Generate hierarchical rule-based symbology grouped by annotation field (root concept), including ancestors and leaves."""
        self.symbology_manager.generate_rule_based_symbology()

    # All these functions are now imported directly from their respective modules
    # The methods above were wrappers that are no longer needed

# REQUIRED ENTRY POINT FOR QGIS — DO NOT REMOVE!
def classFactory(iface):
    return qskos(iface)
