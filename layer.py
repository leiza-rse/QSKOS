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

from .hierarchy import (
    build_concept_tree_from_layer,
    get_filtered_descendant_uris_fast,
)
from .fields import parse_field_value
from .gpkg import (
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
        self.bound_vocab_list    = None
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

        # Bound vocabulary list
        layout.addWidget(QLabel("<b>Bound Vocabularies</b>"))
        self.bound_vocab_list = QListWidget()
        self.bound_vocab_list.setMaximumHeight(100)
        self.bound_vocab_list.currentItemChanged.connect(
            self._on_bound_vocab_selection_changed
        )
        layout.addWidget(self.bound_vocab_list)

        btn_row = QHBoxLayout()
        bind_btn = QPushButton("Bind Vocabulary")
        bind_btn.clicked.connect(self._on_bind_vocab_clicked)
        btn_row.addWidget(bind_btn)
        unbind_btn = QPushButton("Unbind Selected")
        unbind_btn.clicked.connect(self._on_unbind_vocab_clicked)
        btn_row.addWidget(unbind_btn)
        layout.addLayout(btn_row)

        # Concept hierarchy tree
        self.tree_view = QTreeWidget()
        self.tree_view.setHeaderLabel("Concept Hierarchy")
        self.tree_view.itemChanged.connect(self.plugin.on_tree_item_changed)
        layout.addWidget(self.tree_view)

        tab = QWidget()
        tab.setLayout(layout)
        return tab

    # ── Bound vocab list interactions ──────────────────────────────────────────

    def _on_bind_vocab_clicked(self):
        """Show available vocabs from the active GPKG and bind the chosen one."""
        if not self.plugin.active_gpkg_path:
            QMessageBox.warning(None, "No GeoPackage",
                "Select a GeoPackage in the GeoPackage tab first.")
            return

        feature_layer = self.feature_layer_combo.currentLayer()
        if not feature_layer:
            QMessageBox.warning(None, "No Feature Layer",
                "Select a feature layer first.")
            return

        feature_table = layer_table_name(feature_layer)
        if not feature_table:
            QMessageBox.warning(None, "Invalid Layer",
                "The selected layer does not appear to be a GeoPackage table.\n"
                "Load the layer from the active GeoPackage.")
            return

        already_bound = set(
            get_bound_vocab_schemes(self.plugin.active_gpkg_path, feature_table)
        )
        available = [
            r for r in get_vocab_entries(self.plugin.active_gpkg_path)
            if r["scheme_uri"] not in already_bound
        ]
        if not available:
            QMessageBox.information(None, "No Vocabularies Available",
                "All vocabularies in this GeoPackage are already bound,\n"
                "or none have been imported yet.\n\n"
                "Import a vocabulary in the Vocabulary tab first.")
            return

        items = [f"{r['layer_name']}  —  {r['scheme_uri']}" for r in available]
        choice, ok = QInputDialog.getItem(
            None, "Bind Vocabulary",
            "Select vocabulary to bind to this layer:",
            items, 0, False,
        )
        if not ok:
            return

        idx        = items.index(choice)
        scheme_uri = available[idx]["scheme_uri"]
        table_name = available[idx]["layer_name"]

        bind_feature_to_vocab(
            self.plugin.active_gpkg_path, feature_table, scheme_uri
        )
        list_item = QListWidgetItem(f"{table_name}  —  {scheme_uri}")
        list_item.setData(Qt.UserRole, scheme_uri)
        self.bound_vocab_list.addItem(list_item)
        self.bound_vocab_list.setCurrentItem(list_item)

    def _on_unbind_vocab_clicked(self):
        """
        Remove the selected vocab binding from the config table.
        Annotation columns on the feature layer are NOT deleted — users
        remove them manually via the layer attribute table.
        """
        if not self.bound_vocab_list:
            return
        current = self.bound_vocab_list.currentItem()
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

        unbind_feature_from_vocab(
            self.plugin.active_gpkg_path, feature_table, scheme_uri
        )
        self.bound_vocab_list.takeItem(self.bound_vocab_list.row(current))

        # Clear the tree if we just unbound the currently displayed vocab
        if self.plugin.current_vocab_scheme == scheme_uri:
            self._clear_tree()
            self.plugin.current_vocab_layer  = None
            self.plugin.current_vocab_scheme = None

    def _on_bound_vocab_selection_changed(self, current, previous):
        """Load the concept hierarchy tree for whichever vocab is selected."""
        if not current:
            self._clear_tree()
            self.plugin.current_vocab_layer  = None
            self.plugin.current_vocab_scheme = None
            return

        scheme_uri = current.data(Qt.UserRole)
        table_name = find_vocab_table_for_scheme(
            self.plugin.active_gpkg_path, scheme_uri
        )
        if not table_name:
            return
        try:
            vocab_layer = ensure_vocab_layer_loaded(
                self.plugin.active_gpkg_path, table_name
            )
            self.plugin.current_vocab_scheme = scheme_uri
            self.plugin.get_hierarchy_for_layer(vocab_layer)  # pre-warm cache
            self.load_concept_tree(self.plugin.current_feature_layer, vocab_layer)
        except Exception as e:
            QMessageBox.warning(None, "Vocabulary Load Error",
                f"Could not load vocabulary:\n{e}")

    # ── Feature layer change ───────────────────────────────────────────────────

    def on_feature_layer_changed(self, layer):
        """Called when the feature layer combo selection changes."""
        if self.bound_vocab_list:
            self.bound_vocab_list.clear()
        self._clear_tree()

        self.plugin.current_feature_layer = layer
        self.plugin.current_vocab_layer   = None
        self.plugin.current_vocab_scheme  = None

        if not layer or not self.plugin.active_gpkg_path:
            return

        feature_table = layer_table_name(layer)
        if not feature_table:
            return

        # Populate bound vocab list from config
        for scheme_uri in get_bound_vocab_schemes(
            self.plugin.active_gpkg_path, feature_table
        ):
            table_name = find_vocab_table_for_scheme(
                self.plugin.active_gpkg_path, scheme_uri
            )
            if not table_name:
                continue
            item = QListWidgetItem(f"{table_name}  —  {scheme_uri}")
            item.setData(Qt.UserRole, scheme_uri)
            self.bound_vocab_list.addItem(item)

        # Auto-select the first bound vocab so the tree is immediately populated
        if self.bound_vocab_list and self.bound_vocab_list.count() > 0:
            self.bound_vocab_list.setCurrentRow(0)

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