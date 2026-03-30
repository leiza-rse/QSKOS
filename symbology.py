# symbology.py
# qskos QGIS Plugin - Symbology Tab Logic
# Generates hierarchical rule-based symbology from annotation fields.
# Covers ALL vocabularies bound to the current feature layer automatically —
# the user does not need to be viewing any particular vocab in the tree.

import random

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QMessageBox
)
from PyQt5.QtGui import QColor
from qgis.core import (
    QgsRuleBasedRenderer, QgsSymbol, QgsWkbTypes, QgsSingleSymbolRenderer
)

from .hierarchy import get_descendant_uris_fast, get_filtered_descendant_uris_fast
from .fields import parse_field_value
from .gpkg import (
    get_bound_vocab_schemes, find_vocab_table_for_scheme,
    ensure_vocab_layer_loaded, layer_table_name,
)


class SymbologyManager:
    def __init__(self, plugin_instance):
        self.plugin = plugin_instance
        self.symbology_status_label = None

    # ── Tab setup ──────────────────────────────────────────────────────────────

    def setup_symbology_tab(self):
        """Build and return the Symbology tab widget."""
        layout = QVBoxLayout()
        layout.addWidget(QLabel(
            "Generate hierarchical rule-based symbology grouped by annotation "
            "fields.\nAll bound vocabularies are included automatically."
        ))

        gen_btn = QPushButton("Generate Rules from Annotations")
        gen_btn.clicked.connect(self.generate_rule_based_symbology)
        layout.addWidget(gen_btn)

        reset_btn = QPushButton("Reset to Default Symbology")
        reset_btn.clicked.connect(self.reset_symbology)
        layout.addWidget(reset_btn)

        self.symbology_status_label = QLabel(
            "Select a feature layer with annotation fields."
        )
        layout.addWidget(self.symbology_status_label)
        layout.addStretch()

        tab = QWidget()
        tab.setLayout(layout)
        return tab

    # ── Helpers ────────────────────────────────────────────────────────────────

    def reset_symbology(self):
        """Reset the feature layer to a default single-symbol renderer."""
        layer = self.plugin.current_feature_layer
        if not layer:
            QMessageBox.warning(None, "No Layer", "No feature layer selected.")
            return
        layer.setRenderer(QgsSingleSymbolRenderer(
            QgsSymbol.defaultSymbol(layer.geometryType())
        ))
        layer.triggerRepaint()
        self.plugin.iface.layerTreeView().refreshLayerSymbology(layer.id())
        self.symbology_status_label.setText("✅ Symbology reset to default.")
        QMessageBox.information(None, "Reset", "Symbology reset to default.")

    def random_color(self):
        return QColor(
            random.randint(0, 255),
            random.randint(0, 255),
            random.randint(0, 255),
        )

    def _default_symbol(self, geom_type):
        """Return a default symbol for geom_type, with a Point fallback."""
        return (
            QgsSymbol.defaultSymbol(geom_type)
            or QgsSymbol.defaultSymbol(QgsWkbTypes.PointGeometry)
        )

    # ── Symbology generation ───────────────────────────────────────────────────

    def generate_rule_based_symbology(self):
        """
        Generate hierarchical rule-based symbology for the current feature layer.

        Annotation fields are detected by scanning the feature layer's existing
        field names and matching them against concept URIs across ALL bound
        vocabularies.  The currently displayed tree vocab does not matter here.
        """
        layer = self.plugin.current_feature_layer
        if not layer:
            QMessageBox.warning(None, "No Layer",
                "Please select a feature layer first.")
            return
        if not self.plugin.active_gpkg_path:
            QMessageBox.warning(None, "No GeoPackage", "No active GeoPackage.")
            return

        geom_type = layer.geometryType()
        if geom_type == QgsWkbTypes.UnknownGeometry:
            QMessageBox.warning(None, "Invalid Geometry",
                "Cannot generate symbology for a layer with unknown geometry type.")
            return

        feature_table = layer_table_name(layer)
        bound_schemes = get_bound_vocab_schemes(
            self.plugin.active_gpkg_path, feature_table
        )
        if not bound_schemes:
            QMessageBox.warning(None, "No Vocabulary",
                "Layer is not bound to any vocabulary.")
            return

        # ── Merge hierarchies from all bound vocabularies ──────────────────────
        combined_children_map   = {None: []}
        combined_concept_labels = {}

        for scheme_uri in bound_schemes:
            table_name = find_vocab_table_for_scheme(
                self.plugin.active_gpkg_path, scheme_uri
            )
            if not table_name:
                continue
            try:
                vocab_layer = ensure_vocab_layer_loaded(
                    self.plugin.active_gpkg_path, table_name
                )
            except Exception as e:
                print(f"[qskos] Skipping vocab {scheme_uri}: {e}")
                continue

            children_map, concept_labels = self.plugin.get_hierarchy_for_layer(
                vocab_layer
            )
            # Merge into combined maps (union, no duplicates)
            for parent, children in children_map.items():
                if parent not in combined_children_map:
                    combined_children_map[parent] = []
                for child in children:
                    if child not in combined_children_map[parent]:
                        combined_children_map[parent].append(child)
            combined_concept_labels.update(concept_labels)

        # ── Detect annotation fields ───────────────────────────────────────────
        # Any feature layer field whose name is a known concept URI is an
        # annotation field — independent of tree checkbox state.
        existing_field_names = [f.name() for f in layer.fields()]
        annotation_field_uris = [
            uri for uri in existing_field_names
            if uri in combined_concept_labels
        ]

        if not annotation_field_uris:
            QMessageBox.warning(None, "No Annotations",
                "No annotation fields found matching any bound vocabulary.\n"
                "Check concepts in the Layer tab to create annotation fields first.")
            return

        # uri → broader lookup for ancestor walking
        uri_to_broader = {
            child: parent
            for parent, children in combined_children_map.items()
            for child in children
        }

        field_to_descendants = {
            field_uri: set(
                get_descendant_uris_fast(combined_children_map, field_uri)
            )
            for field_uri in annotation_field_uris
        }

        root_rule = QgsRuleBasedRenderer.Rule(None)

        for field_uri in annotation_field_uris:
            field_label = combined_concept_labels.get(field_uri, field_uri)
            if layer.fields().lookupField(field_uri) == -1:
                continue

            # Collect URIs actually present in this field across all features
            directly_annotated = set()
            valid_descendants   = field_to_descendants[field_uri]
            for feat in layer.getFeatures():
                for uri in parse_field_value(feat[field_uri]):
                    if uri in valid_descendants:
                        directly_annotated.add(uri)

            # Walk up to collect ancestor concepts between leaf and field root
            def get_ancestors(uri, _field_uri=field_uri):
                ancestors, visited, current = [], set(), uri
                while current and current != _field_uri and current not in visited:
                    visited.add(current)
                    parent = uri_to_broader.get(current)
                    if not parent or parent == current:
                        break
                    ancestors.append(parent)
                    if parent == _field_uri:
                        break
                    current = parent
                return ancestors

            # Concepts to visualise: annotated leaves + their ancestors
            concepts_to_visualize = set()
            for uri in directly_annotated:
                concepts_to_visualize.add(uri)
                for anc in get_ancestors(uri):
                    if anc in valid_descendants:
                        concepts_to_visualize.add(anc)

            if not concepts_to_visualize:
                continue

            all_desc = get_filtered_descendant_uris_fast(
                combined_children_map, field_uri
            )
            if not all_desc:
                continue

            # Helper: build an array_contains clause for one URI in this field
            def _clause(u, _furi=field_uri):
                safe = u.replace("'", "''")
                return f'array_contains("{_furi}", \'{safe}\')'

            # Group rule: matches any feature with a value in this field's subtree
            group_sym = self._default_symbol(geom_type)
            group_sym.setColor(self.random_color())
            group_rule = QgsRuleBasedRenderer.Rule(
                symbol=group_sym,
                filterExp=" OR ".join(_clause(u) for u in all_desc),
                label=field_label,
                description="Group: all descendants",
            )
            group_rule.setActive(True)

            # "All" rule for the field root (includes self + all descendants)
            desc_incl = get_descendant_uris_fast(combined_children_map, field_uri)
            if desc_incl:
                sym_all = self._default_symbol(geom_type)
                sym_all.setColor(self.random_color())
                all_rule = QgsRuleBasedRenderer.Rule(
                    symbol=sym_all,
                    filterExp=" OR ".join(_clause(u) for u in desc_incl),
                    label=f"{field_label} (All)",
                    description="Field concept and all its descendants",
                )
                all_rule.setActive(True)
                group_rule.appendChild(all_rule)

            # Child rules — one per concept in concepts_to_visualize
            processed = {field_uri}
            for uri in concepts_to_visualize:
                if uri in processed:
                    continue
                processed.add(uri)

                uri_label = combined_concept_labels.get(uri, uri)
                desc_uris = get_descendant_uris_fast(combined_children_map, uri)
                if not desc_uris:
                    continue

                sym_child = self._default_symbol(geom_type)
                sym_child.setColor(self.random_color())
                child_rule = QgsRuleBasedRenderer.Rule(
                    symbol=sym_child,
                    filterExp=" OR ".join(_clause(u) for u in desc_uris),
                    label=uri_label,
                    description="",
                )
                child_rule.setActive(True)
                group_rule.appendChild(child_rule)

            # Else rule for unannotated features within this group
            sym_else = self._default_symbol(geom_type)
            sym_else.setColor(QColor(200, 200, 200))
            else_rule = QgsRuleBasedRenderer.Rule(
                symbol=sym_else,
                filterExp="",
                label="(Unannotated)",
                description="",
                elseRule=True,
            )
            else_rule.setActive(True)
            group_rule.appendChild(else_rule)

            root_rule.appendChild(group_rule)

        if root_rule.children():
            layer.setRenderer(QgsRuleBasedRenderer(root_rule))
            layer.triggerRepaint()
            self.plugin.iface.layerTreeView().refreshLayerSymbology(layer.id())
            n = len(annotation_field_uris)
            QMessageBox.information(None, "Success",
                f"Generated hierarchical symbology for {n} annotation field(s).")
            self.symbology_status_label.setText(
                f"✅ Generated symbology for {n} field(s)."
            )
        else:
            QMessageBox.information(None, "No Data",
                "No annotation values found to generate symbology.")