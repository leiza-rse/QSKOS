# symbology.py
# qskos QGIS Plugin - Symbology Tab Logic
# Handles rule-based symbology generation

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel
)
from PyQt5.QtCore import Qt, QVariant
from PyQt5.QtWidgets import QMessageBox
from qgis.core import QgsProject, QgsMapLayer, QgsRuleBasedRenderer, QgsSymbol, QgsWkbTypes, QgsExpression, QgsSingleSymbolRenderer, QgsFeatureRequest
from PyQt5.QtGui import QColor
import random

# Import utility functions from separate module
from .qskos_utils import (
    get_descendant_uris_fast,
    get_filtered_descendant_uris_fast
)


class SymbologyManager:
    def __init__(self, plugin_instance):
        self.plugin = plugin_instance
        self.generate_symbology_button = None
        self.reset_symbology_button = None
        self.symbology_status_label = None
        
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

        symbology_tab = QWidget()
        symbology_tab.setLayout(layout)
        return symbology_tab

    def reset_symbology(self):
        """Reset layer symbology to default single symbol."""
        layer = self.plugin.current_feature_layer
        if not layer:
            QMessageBox.warning(None, "No Layer", "No feature layer selected.")
            return

        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        renderer = QgsSingleSymbolRenderer(symbol)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        self.plugin.iface.layerTreeView().refreshLayerSymbology(layer.id())
        QMessageBox.information(None, "Reset", "Symbology reset to default.")
        self.symbology_status_label.setText("✅ Symbology reset to default.")

    def get_checked_concept_uris(self):
        """Recursively get all checked concept URIs from the tree view."""
        if not self.plugin.layer_manager.tree_view:
            return []
        root = self.plugin.layer_manager.tree_view.invisibleRootItem()
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

    def generate_rule_based_symbology(self):
        """Generate hierarchical rule-based symbology grouped by annotation field (root concept), including ancestors and leaves."""
        layer = self.plugin.current_feature_layer
        vocab_layer = self.plugin.current_vocab_layer
        if not layer:
            QMessageBox.warning(None, "No Layer", "Please select a feature layer first.")
            return
        if not vocab_layer:
            QMessageBox.warning(None, "No Vocabulary", "Layer is not bound to a vocabulary.")
            return

        # Check if the layer has a valid geometry type for symbology
        geom_type = layer.geometryType()
        if geom_type == QgsWkbTypes.UnknownGeometry:
             QMessageBox.warning(None, "Invalid Geometry", "Cannot generate symbology for layer with unknown geometry type.")
             return

        # Get all checked root concepts → these are our field groups
        checked_uris = self.get_checked_concept_uris()
        if not checked_uris:
            QMessageBox.warning(None, "No Annotations", "No checked vocabulary concepts found. Please check some in the Layer tab.")
            return

        # 👇 Use precomputed hierarchy for fast lookups
        children_map, concept_labels = self.plugin.get_hierarchy_for_layer(vocab_layer)

        # Build uri_to_broader from children_map
        uri_to_broader = {}
        for parent, children in children_map.items():
            for child in children:
                uri_to_broader[child] = parent  # parent can be None

        # Build root → descendants map for each field
        field_to_descendants = {}
        for field_uri in checked_uris:
            descendants = set(get_descendant_uris_fast(children_map, field_uri))
            field_to_descendants[field_uri] = descendants

        # Root rule for renderer
        root_rule = QgsRuleBasedRenderer.Rule(None) # Root rule typically has no symbol/filter

        for field_uri in checked_uris:
            field_label = concept_labels.get(field_uri, field_uri)
            field_index = layer.fields().lookupField(field_uri)
            if field_index == -1:
                continue

            # Get all URIs used in this field across all features
            directly_annotated_uris = set()
            valid_descendants = field_to_descendants[field_uri]
            for feat in layer.getFeatures():
                val = feat[field_uri]
                uri_list = self.plugin.parse_field_value(val)
                # Filter URIs to only those valid for this field's hierarchy
                uri_list = [u for u in uri_list if u in valid_descendants]
                for uri in uri_list:
                    directly_annotated_uris.add(uri)

            # Helper to get ancestors up to (but not including) field root
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
                concepts_to_visualize.add(uri)  # ← INCLUDES LEAVES
                ancestors = get_ancestors(uri)
                for anc in ancestors:
                    if anc in field_to_descendants[field_uri]:
                        concepts_to_visualize.add(anc)  # ← INCLUDES INTERMEDIATES

            # Skip if nothing to visualize for this field
            if not concepts_to_visualize:
                continue

            # --- ✅ GROUP RULE for the field root (even if not directly annotatable) ---
            # Get all descendant URIs — EXCLUDE root (since it's not annotatable in widget)
            all_descendant_uris = get_filtered_descendant_uris_fast(children_map, field_uri)
            if not all_descendant_uris:
                continue # Shouldn't happen if concepts_to_visualize exists, but safe check

            # Build OR expression using array_contains for the GROUP rule
            or_clauses_root = [f'array_contains("{field_uri}", \'{u.replace("'", "''")}\')' for u in all_descendant_uris]
            expr_str_root = " OR ".join(or_clauses_root) if or_clauses_root else "0"

            # Create symbol for group rule
            group_symbol = QgsSymbol.defaultSymbol(geom_type) # Use geometry type
            if group_symbol is None:
                 # Fallback if defaultSymbol fails unexpectedly
                 group_symbol = QgsSymbol.defaultSymbol(QgsWkbTypes.PointGeometry)
            group_symbol.setColor(self.random_color())

            # Create group rule using DIRECT CONSTRUCTOR (without 'active' kwarg)
            group_rule = QgsRuleBasedRenderer.Rule(
                symbol=group_symbol, # Pass the symbol object directly
                filterExp=expr_str_root, # Expression string
                label=field_label, # Label for the rule
                description='Group: All descendants' # Description
                # Note: 'active' keyword argument removed
            )
            group_rule.setActive(True) # Set active using method

            # --- ✅ CHILD RULES ---
            # Create a rule for the field_uri itself if concepts are visualized
            # This ensures the top level of the hierarchy is represented as a rule.
            # Get descendants for the field_uri rule (including itself)
            desc_uris_for_field_uri = get_descendant_uris_fast(children_map, field_uri) # Includes field_uri itself
            if desc_uris_for_field_uri: # Should be true if concepts_to_visualize exists
                or_clauses_field_uri = [f'array_contains("{field_uri}", \'{u.replace("'", "''")}\')' for u in desc_uris_for_field_uri]
                expr_str_field_uri = " OR ".join(or_clauses_field_uri) if or_clauses_field_uri else "0"
                symbol_field_uri = QgsSymbol.defaultSymbol(geom_type) # Use geometry type
                if symbol_field_uri is None:
                     symbol_field_uri = QgsSymbol.defaultSymbol(QgsWkbTypes.PointGeometry)
                symbol_field_uri.setColor(self.random_color()) # Or use a distinct color

                # Create field_uri rule using DIRECT CONSTRUCTOR (without 'active' kwarg)
                field_uri_rule = QgsRuleBasedRenderer.Rule(
                    symbol=symbol_field_uri,
                    filterExp=expr_str_field_uri,
                    label=f"{field_label} (All)", # Label for the field concept rule
                    description='Represents the field concept and all its descendants used in annotations'
                    # Note: 'active' keyword argument removed
                )
                field_uri_rule.setActive(True) # Set active using method
                group_rule.appendChild(field_uri_rule)

            # Add CHILD RULES for every concept in concepts_to_visualize (INCLUDING LEAVES)
            # Use a set to avoid duplicates if a concept is both directly annotated and an ancestor
            processed_uris = {field_uri} # Add field_uri to avoid re-processing
            for uri in concepts_to_visualize:
                # Skip field_uri - already handled above
                # Also skip if already processed (shouldn't happen with set logic, but safe)
                if uri == field_uri or uri in processed_uris:
                     continue
                processed_uris.add(uri)

                label = concept_labels.get(uri, uri)
                # Get ALL descendants of this concept (including itself) for rule filter
                desc_uris = self.plugin.get_descendant_uris_fast(children_map, uri)
                if not desc_uris:
                    continue  # Shouldn't happen

                # Build expression
                or_clauses = [f'array_contains("{field_uri}", \'{u.replace("'", "''")}\')' for u in desc_uris]
                expr_str = " OR ".join(or_clauses) if or_clauses else "0"
                
                # Create symbol for child rule
                symbol = QgsSymbol.defaultSymbol(geom_type) # Use geometry type
                if symbol is None:
                     symbol = QgsSymbol.defaultSymbol(QgsWkbTypes.PointGeometry)
                symbol.setColor(self.random_color())
                
                # Create child rule using DIRECT CONSTRUCTOR (without 'active' kwarg)
                child_rule = QgsRuleBasedRenderer.Rule(
                    symbol=symbol,
                    filterExp=expr_str,
                    label=label,
                    description=''
                    # Note: 'active' keyword argument removed
                )
                child_rule.setActive(True) # Set active using method
                group_rule.appendChild(child_rule)

            # Add ELSE rule for unannotated features within this field's group
            else_symbol = QgsSymbol.defaultSymbol(geom_type) # Use geometry type
            if else_symbol is None:
                 else_symbol = QgsSymbol.defaultSymbol(QgsWkbTypes.PointGeometry)
            else_symbol.setColor(QColor(200, 200, 200))  # Light gray
            
            # Create else rule using DIRECT CONSTRUCTOR (without 'active' kwarg)
            else_rule = QgsRuleBasedRenderer.Rule(
                symbol=else_symbol,
                filterExp='', # No filter for else rule
                label='(Unannotated)',
                description='',
                elseRule=True # Explicitly mark as else rule
                # Note: 'active' keyword argument removed
            )
            else_rule.setActive(True) # Set active using method (often implicit for else, but safe)
            group_rule.appendChild(else_rule)

            # Add the completed group rule to the main root
            root_rule.appendChild(group_rule)

        if root_rule.children():
            renderer = QgsRuleBasedRenderer(root_rule)
            layer.setRenderer(renderer)
            layer.triggerRepaint()
            self.plugin.iface.layerTreeView().refreshLayerSymbology(layer.id())
            QMessageBox.information(None, "Success", f"Generated hierarchical symbology for {len(checked_uris)} fields.")
            self.symbology_status_label.setText(f"✅ Generated symbology for {len(checked_uris)} fields.")
        else:
            QMessageBox.information(None, "No Data", "No annotation values found to generate symbology.")