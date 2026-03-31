# layer.py
# qskos QGIS Plugin - Layer Tab Logic
# Multi-vocabulary binding, concept hierarchy tree, annotation field creation.

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QTreeWidget, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QInputDialog
)
from PyQt5.QtCore import Qt, QTimer, QVariant
from qgis.core import (
    QgsProject, QgsMapLayer, QgsField,
    QgsEditorWidgetSetup, QgsDefaultValue, QgsMapLayerProxyModel
)
from qgis.gui import QgsMapLayerComboBox

from ..utils.hierarchy import (
    build_concept_tree_from_layer,
    get_filtered_descendant_uris_fast,
)
from ..utils.fields import parse_field_value
from ..utils.gpkg import (
    read_config, get_vocab_entries, get_bound_vocab_schemes,
    find_vocab_table_for_scheme, bind_feature_to_vocab,
    unbind_feature_from_vocab, ensure_vocab_layer_loaded,
    layer_gpkg_path, layer_table_name, norm_path,
    ROLE_VOCAB, F_CONCEPT, F_LABEL, F_DEF,
)


class LayerManager:
    def __init__(self, plugin_instance):
        self.plugin           = plugin_instance
        self.feature_layer_combo = None
        self.vocab_list          = None
        self.tree_view           = None

    # ── Tab setup ──────────────────────────────────────────────────────────────

    def setup_layer_tab(self):
        """Build and return the Layer tab widget."""
        layout = QVBoxLayout()

        # Feature layer selector
        form = QFormLayout()
        self.feature_layer_combo = QgsMapLayerComboBox()
        self.feature_layer_combo.setFilters(
            QgsMapLayerProxyModel.VectorLayer | QgsMapLayerProxyModel.HasGeometry
        )
        self.feature_layer_combo.setAllowEmptyLayer(True)
        self.feature_layer_combo.setShowCrs(True)
        self.feature_layer_combo.layerChanged.connect(
            self.plugin.on_feature_layer_changed
        )
        form.addRow("Feature Layer:", self.feature_layer_combo)
        layout.addLayout(form)

        # Vocabulary management list (shows all vocabularies with binding state)
        layout.addWidget(QLabel("<b>Vocabulary Management</b>"))
        self.vocab_list = QListWidget()
        self.vocab_list.setMaximumHeight(150)
        self.vocab_list.currentItemChanged.connect(
            self._on_vocab_selection_changed
        )
        self.vocab_list.itemChanged.connect(
            self._on_vocab_binding_toggled
        )
        layout.addWidget(self.vocab_list)

        # Unbind button (kept as fallback)
        unbind_btn = QPushButton("Unbind Selected")
        unbind_btn.clicked.connect(self._on_unbind_vocab_clicked)
        layout.addWidget(unbind_btn)

        # Concept hierarchy tree
        self.tree_view = QTreeWidget()
        self.tree_view.setHeaderLabel("Concept Hierarchy")
        self.tree_view.itemChanged.connect(self.plugin.on_tree_item_changed)
        layout.addWidget(self.tree_view)

        tab = QWidget()
        tab.setLayout(layout)
        return tab

    # ── Vocabulary management interactions ─────────────────────────────────────

    def _on_vocab_selection_changed(self, current, previous):
        """Load the concept hierarchy tree only for bound vocabularies."""
        if not current:
            self._clear_tree()
            self.plugin.current_vocab_layer  = None
            self.plugin.current_vocab_scheme = None
            return

        self._load_tree_for_item(current)

    def _load_tree_for_item(self, item):
        """Load the concept hierarchy tree for a vocabulary item if it's bound."""
        if not item:
            self._clear_tree()
            self.plugin.current_vocab_layer  = None
            self.plugin.current_vocab_scheme = None
            return

        scheme_uri = item.data(Qt.UserRole)

        # Check if this vocabulary is bound to the current feature layer
        feature_layer = self.feature_layer_combo.currentLayer()
        if not feature_layer:
            self._clear_tree()
            return

        feature_table = layer_table_name(feature_layer)
        if not feature_table:
            self._clear_tree()
            return

        # Get currently bound vocabularies for this feature layer
        bound_schemes = set(
            get_bound_vocab_schemes(self.plugin.active_gpkg_path, feature_table)
        )

        # Only load tree if the vocabulary is bound
        if scheme_uri not in bound_schemes:
            self._clear_tree()
            return

        table_name = find_vocab_table_for_scheme(
            self.plugin.active_gpkg_path, scheme_uri
        )
        if not table_name:
            self._clear_tree()
            return
        try:
            vocab_layer = ensure_vocab_layer_loaded(
                self.plugin.active_gpkg_path, table_name
            )
            self.plugin.current_vocab_scheme = scheme_uri
            self.plugin.get_hierarchy_for_layer(vocab_layer)  # pre-warm cache
            self.load_concept_tree(self.plugin.current_feature_layer, vocab_layer)
        except Exception as e:
            self._clear_tree()

    def _on_vocab_binding_toggled(self, item):
        """
        Handle checkbox state changes to bind/unbind vocabularies.
        Checkbox only changes binding state - use unbind button for confirmation.
        """
        if not item or not self.plugin.active_gpkg_path:
            return

        scheme_uri = item.data(Qt.UserRole)
        feature_layer = self.feature_layer_combo.currentLayer()
        if not feature_layer:
            item.setCheckState(Qt.Unchecked)
            QMessageBox.warning(None, "No Feature Layer",
                "Select a feature layer first to bind/unbind vocabularies.")
            return

        feature_table = layer_table_name(feature_layer)
        if not feature_table:
            item.setCheckState(Qt.Unchecked)
            QMessageBox.warning(None, "Invalid Layer",
                "The selected layer does not appear to be a GeoPackage table.")
            return

        # Check if the item is being checked (bind) or unchecked (unbind)
        is_checked = item.checkState() == Qt.Checked

        try:
            if is_checked:
                # Bind the vocabulary
                bind_feature_to_vocab(
                    self.plugin.active_gpkg_path, feature_table, scheme_uri
                )
                # If this is the currently selected item, load the tree automatically
                if self.vocab_list.currentItem() == item:
                    self._load_tree_for_item(item)
            else:
                # Unbind the vocabulary - but revert checkbox and show confirmation
                reply = QMessageBox.question(
                    None, "Confirm Unbind",
                    f"Remove binding to:\n'{scheme_uri}'?\n\n"
                    f"Annotation columns on the feature layer will NOT be deleted.\n"
                    f"Remove them manually via the layer attribute table if needed.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    unbind_feature_from_vocab(
                        self.plugin.active_gpkg_path, feature_table, scheme_uri
                    )
                    # Clear the tree if we just unbound the currently displayed vocab
                    if self.plugin.current_vocab_scheme == scheme_uri:
                        self._clear_tree()
                        self.plugin.current_vocab_layer  = None
                        self.plugin.current_vocab_scheme = None
                else:
                    # Revert the checkbox state if user cancelled
                    item.setCheckState(Qt.Checked)

        except Exception as e:
            # Revert the checkbox state if there was an error
            item.setCheckState(Qt.Unchecked if is_checked else Qt.Checked)
            QMessageBox.critical(None, "Operation Failed",
                f"Could not {'bind' if is_checked else 'unbind'} vocabulary:\n{str(e)}")

    def _on_unbind_vocab_clicked(self):
        """
        Remove the selected vocab binding from the config table.
        This is kept as a fallback method but less necessary with the new checkbox approach.
        """
        if not self.vocab_list:
            return
        current = self.vocab_list.currentItem()
        if not current:
            QMessageBox.information(None, "Nothing Selected",
                "Select a vocabulary in the list to unbind.")
            return

        scheme_uri    = current.data(Qt.UserRole)
        feature_layer = self.feature_layer_combo.currentLayer()
        feature_table = layer_table_name(feature_layer) if feature_layer else None
        if not feature_table:
            return

        reply = QMessageBox.question(
            None, "Confirm Unbind",
            f"Remove binding to:\n'{scheme_uri}'?\n\n"
            f"Annotation columns on the feature layer will NOT be deleted.\n"
            f"Remove them manually via the layer attribute table if needed.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            unbind_feature_from_vocab(
                self.plugin.active_gpkg_path, feature_table, scheme_uri
            )
            # Update the checkbox state
            current.setCheckState(Qt.Unchecked)

            # Clear the tree if we just unbound the currently displayed vocab
            if self.plugin.current_vocab_scheme == scheme_uri:
                self._clear_tree()
                self.plugin.current_vocab_layer  = None
                self.plugin.current_vocab_scheme = None

        except Exception as e:
            QMessageBox.critical(None, "Unbind Failed",
                f"Could not unbind vocabulary:\n{str(e)}")

    # ── Feature layer change ───────────────────────────────────────────────────

    def on_feature_layer_changed(self, layer):
        """Called when the feature layer combo selection changes."""
        if self.vocab_list:
            self.vocab_list.clear()
        self._clear_tree()

        self.plugin.current_feature_layer = layer
        self.plugin.current_vocab_layer   = None
        self.plugin.current_vocab_scheme  = None

        if not layer or not self.plugin.active_gpkg_path:
            return

        feature_table = layer_table_name(layer)
        if not feature_table:
            return

        # Populate unified vocabulary list with all available vocabularies
        self._refresh_vocabulary_list(feature_table)

    def _refresh_vocabulary_list(self, feature_table):
        """
        Populate the vocabulary list with all available vocabularies,
        showing their binding state with checkboxes.
        """
        if not self.plugin.active_gpkg_path:
            return

        # Get all vocabularies in the GeoPackage
        all_vocabs = get_vocab_entries(self.plugin.active_gpkg_path)
        if not all_vocabs:
            return

        # Get currently bound vocabularies for this feature layer
        bound_schemes = set(
            get_bound_vocab_schemes(self.plugin.active_gpkg_path, feature_table)
        )

        # Add all vocabularies to the list with appropriate checkbox state
        for vocab in all_vocabs:
            scheme_uri = vocab["scheme_uri"]
            table_name = vocab["layer_name"]

            item = QListWidgetItem(f"{table_name}  —  {scheme_uri}")
            item.setData(Qt.UserRole, scheme_uri)

            # Set checkbox state based on whether this vocabulary is bound
            if scheme_uri in bound_schemes:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)

            # Make items checkable
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)

            self.vocab_list.addItem(item)

        # Auto-select the first vocabulary so the tree is immediately populated
        if self.vocab_list and self.vocab_list.count() > 0:
            self.vocab_list.setCurrentRow(0)


    # ── Tree management ────────────────────────────────────────────────────────

    def _clear_tree(self):
        """Clear the tree with signals blocked to avoid spurious field creation."""
        if self.tree_view:
            self.tree_view.blockSignals(True)
            self.tree_view.clear()
            self.tree_view.blockSignals(False)

    def load_concept_tree(self, feature_layer, vocab_layer):
        """
        Populate the tree with the concept hierarchy for vocab_layer.

        Signal blocking wraps the entire build+restore cycle so that
        setCheckState() calls in restore_checked_concepts() do NOT fire
        on_tree_item_changed() — which would create annotation fields for
        every already-existing field on every tree load.
        """
        if not self.tree_view:
            return

        self.tree_view.blockSignals(True)
        self.tree_view.clear()

        self.plugin.current_feature_layer = feature_layer
        self.plugin.current_vocab_layer   = vocab_layer
        self.plugin.get_hierarchy_for_layer(vocab_layer)  # pre-warm cache

        for item in build_concept_tree_from_layer(vocab_layer):
            self.tree_view.addTopLevelItem(item)

        if feature_layer:
            existing_fields = [f.name() for f in feature_layer.fields()]
            self.restore_checked_concepts(
                self.tree_view.invisibleRootItem(), existing_fields
            )

        self.tree_view.blockSignals(False)

    def restore_checked_concepts(self, parent_item, existing_uris):
        """Recursively check tree items whose URI matches an existing field name."""
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.data(0, Qt.UserRole) in existing_uris:
                child.setCheckState(0, Qt.Checked)
            self.restore_checked_concepts(child, existing_uris)

    # ── Annotation field creation ──────────────────────────────────────────────

    def create_annotation_field(self, concept_uri, label):
        """
        Add a Map-type annotation field named concept_uri to the feature layer,
        with a ValueRelation widget showing descendants of concept_uri.
        """
        if not self.plugin.current_feature_layer or not self.plugin.current_vocab_layer:
            return
        if self.plugin.current_feature_layer.fields().lookupField(concept_uri) != -1:
            return  # Field already exists — nothing to do

        layer = self.plugin.current_feature_layer
        layer.startEditing()
        layer.addAttribute(QgsField(concept_uri, QVariant.Map))
        layer.updateFields()

        field_index = layer.fields().lookupField(concept_uri)
        layer.setDefaultValueDefinition(
            field_index, QgsDefaultValue("array()", True)
        )

        # ValueRelation filter: descendants of concept_uri, excluding itself
        children_map, _ = self.plugin.get_hierarchy_for_layer(
            self.plugin.current_vocab_layer
        )
        target_uris = get_filtered_descendant_uris_fast(children_map, concept_uri)

        if not target_uris:
            filter_expression = "0"   # concept has no descendants — widget shows nothing
        else:
            quoted = ["'" + u.replace("'", "''") + "'" for u in target_uris]
            filter_expression = f'"{F_CONCEPT}" IN ({",".join(quoted)})'

        config = {
            "Layer":            self.plugin.current_vocab_layer.id(),
            "Key":              F_CONCEPT,   # stored value: concept URI
            "Value":            F_LABEL,     # displayed: prefLabel
            "Description":      F_DEF,       # tooltip: definition
            "FilterExpression": filter_expression,
            "AllowMulti":       True,
            "UseCompleter":     True,
            "OrderByValue":     True,
        }
        layer.setEditorWidgetSetup(
            field_index, QgsEditorWidgetSetup("ValueRelation", config)
        )
        layer.setFieldAlias(field_index, label)
        layer.commitChanges()

        QMessageBox.information(None, "Field Created",
            f"Annotation field '{label}' created.")

    # ── Layer combo refresh ────────────────────────────────────────────────────

    def refresh_layer_combos(self):
        """
        Rebuild the feature layer combo exception list so it shows only
        geometry layers from the active GPKG, excluding vocab attribute tables.

        Pure logic — no visibility check — so it is safe to call directly
        from tests without a running Qt event loop.
        """
        try:
            all_layers = list(QgsProject.instance().mapLayers().values())

            vocab_table_names = set()
            if self.plugin.active_gpkg_path:
                vocab_table_names = {
                    r["layer_name"]
                    for r in read_config(self.plugin.active_gpkg_path)
                    if r["layer_role"] == ROLE_VOCAB
                }

            if not self.feature_layer_combo:
                return

            excepted = []
            for layer in all_layers:
                if layer.type() != QgsMapLayer.VectorLayer:
                    excepted.append(layer)
                    continue
                # Exclude vocab attribute tables
                if layer_table_name(layer) in vocab_table_names:
                    excepted.append(layer)
                    continue
                # If a GPKG is active, exclude layers not from it
                if self.plugin.active_gpkg_path and (
                    norm_path(layer_gpkg_path(layer))
                    != norm_path(self.plugin.active_gpkg_path)
                ):
                    excepted.append(layer)

            self.feature_layer_combo.setExceptedLayerList(excepted)

        except RuntimeError:
            pass  # Widget was deleted — safe to ignore
        except Exception as e:
            print(f"[qskos] refresh_layer_combos error: {e}")

    def schedule_refresh(self):
        """Defer refresh to the next event loop tick to avoid reentrancy."""
        if self.plugin.dock_widget:
            QTimer.singleShot(0, self.refresh_layer_combos)