# layer.py
# qskos QGIS Plugin - Layer Tab Logic
# Binds vocabularies to a feature layer, shows the concept tree of the selected
# vocabulary and turns ticked concepts into annotation fields.
#
# State owned by this tab:
#   plugin.state.current_feature_layer  the layer chosen in the combo (shared:
#                                       the Symbology tab acts on it too)
#   self._shown_scheme / _shown_vocab   the vocabulary whose tree is displayed,
#                                       set ONLY by selecting it in the list
# Every handler derives what it needs from these two; nothing else is cached.

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QPushButton, QTreeWidget,
    QTreeWidgetItem, QLabel, QListWidget, QListWidgetItem, QMessageBox,
)
from PyQt5.QtCore import Qt, QTimer
from qgis.core import QgsProject, QgsMapLayer, QgsMapLayerProxyModel
from qgis.gui import QgsMapLayerComboBox

from ..utils.annotation import (
    bind_annotation_widgets,
    create_annotation_field,
)
from ..utils.gpkg import (
    read_config, get_vocab_entries, get_bound_vocab_schemes,
    find_vocab_table_for_scheme, bind_feature_to_vocab,
    unbind_feature_from_vocab, norm_path, ROLE_VOCAB,
)
from ..utils.layers import (
    ensure_vocab_layer_loaded, layer_gpkg_path, layer_table_name,
)
from ..utils.logging import log, LEVEL_WARNING


def build_concept_tree_items(vocab_layer):
    """
    Build checkable QTreeWidgetItems for a vocab layer and return the roots
    (concepts without a broader concept inside the vocabulary).
    """
    items, parents = {}, {}
    for feat in vocab_layer.getFeatures():
        uri = feat["concept"]
        item = QTreeWidgetItem([feat["prefLabel"] or uri])
        item.setData(0, Qt.UserRole, uri)
        item.setToolTip(0, uri)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Unchecked)
        items[uri] = item
        parents[uri] = feat["broader"] or None

    roots = []
    for uri, item in items.items():
        parent = parents[uri]
        if parent in items and parent != uri:
            items[parent].addChild(item)
        else:
            roots.append(item)
    return roots


def _iter_tree(parent):
    for i in range(parent.childCount()):
        child = parent.child(i)
        yield child
        yield from _iter_tree(child)


def _confirm_unbind(scheme_uri):
    reply = QMessageBox.question(
        None, "Confirm Unbind",
        f"Remove binding to:\n'{scheme_uri}'?\n\n"
        f"Annotation columns on the feature layer will NOT be deleted.\n"
        f"Remove them manually via the layer attribute table if needed.",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    return reply == QMessageBox.Yes


class LayerManager:
    def __init__(self, plugin_instance):
        self.plugin = plugin_instance
        self.feature_layer_combo = None
        self.vocab_list = None
        self.tree_view = None
        self.hint_label = None
        self._shown_scheme = None
        self._shown_vocab = None

    # ── Convenience ────────────────────────────────────────────────────────────

    @property
    def _gpkg(self):
        return self.plugin.state.active_gpkg_path

    @property
    def _layer(self):
        return self.plugin.state.current_feature_layer

    def _feature_table(self):
        return layer_table_name(self._layer) if self._layer else ""

    def _bound_schemes(self):
        table = self._feature_table()
        if not (self._gpkg and table):
            return set()
        return set(get_bound_vocab_schemes(self._gpkg, table))

    def _hint(self, text):
        if self.hint_label:
            self.hint_label.setText(text)

    # ── Tab setup ──────────────────────────────────────────────────────────────

    def setup_layer_tab(self):
        """Build and return the Layer tab widget."""
        layout = QVBoxLayout()

        form = QFormLayout()
        self.feature_layer_combo = QgsMapLayerComboBox()
        self.feature_layer_combo.setFilters(
            QgsMapLayerProxyModel.VectorLayer | QgsMapLayerProxyModel.HasGeometry
        )
        self.feature_layer_combo.setAllowEmptyLayer(True)
        self.feature_layer_combo.setShowCrs(True)
        self.feature_layer_combo.layerChanged.connect(self.on_feature_layer_changed)
        form.addRow("Feature Layer:", self.feature_layer_combo)
        layout.addLayout(form)

        layout.addWidget(QLabel("<b>Vocabularies</b> (tick to bind to the layer)"))
        self.vocab_list = QListWidget()
        self.vocab_list.setMaximumHeight(150)
        self.vocab_list.currentItemChanged.connect(self._on_vocab_selected)
        self.vocab_list.itemChanged.connect(self._on_vocab_check_toggled)
        layout.addWidget(self.vocab_list)

        unbind_btn = QPushButton("Unbind Selected")
        unbind_btn.clicked.connect(self._on_unbind_clicked)
        layout.addWidget(unbind_btn)

        self.tree_view = QTreeWidget()
        self.tree_view.setHeaderLabel("Concept Hierarchy")
        self.tree_view.itemChanged.connect(self._on_tree_item_changed)
        layout.addWidget(self.tree_view)

        self.hint_label = QLabel("")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        tab = QWidget()
        tab.setLayout(layout)
        return tab

    # ── Feature layer ──────────────────────────────────────────────────────────

    def on_feature_layer_changed(self, layer):
        """Combo selection changed: re-point widgets and rebuild the list."""
        if layer is self._layer and layer is not None:
            # QgsMapLayerComboBox re-emits the same layer when its filter is
            # refreshed (e.g. after a vocab layer is added to the project).
            # Rebuilding here used to reset the list and hide the tree.
            return
        self.plugin.state.current_feature_layer = layer
        self._shown_scheme = None
        if layer is not None:
            self.reinitialize_all_annotation_fields_for_layer(layer)
        self.refresh_vocab_list()

    # ── Vocabulary list ────────────────────────────────────────────────────────

    def refresh_vocab_list(self):
        """
        Rebuild the vocabulary list for the current feature layer from the GPKG
        config (call after imports / GPKG changes).  Keeps the displayed
        vocabulary selected if it still exists, else selects the first one.
        """
        if self.vocab_list is None:
            return
        keep = self._shown_scheme
        self.vocab_list.blockSignals(True)
        try:
            self.vocab_list.clear()
            if self._gpkg and self._feature_table():
                bound = self._bound_schemes()
                for vocab in get_vocab_entries(self._gpkg):
                    scheme = vocab["scheme_uri"]
                    item = QListWidgetItem(f"{vocab['layer_name']}  —  {scheme}")
                    item.setData(Qt.UserRole, scheme)
                    item.setToolTip(scheme)
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Checked if scheme in bound else Qt.Unchecked)
                    self.vocab_list.addItem(item)
            row = next(
                (i for i in range(self.vocab_list.count())
                 if self.vocab_list.item(i).data(Qt.UserRole) == keep),
                0,
            )
            if self.vocab_list.count():
                self.vocab_list.setCurrentRow(row)
        finally:
            self.vocab_list.blockSignals(False)

        current = self.vocab_list.currentItem()
        self.show_vocab(current.data(Qt.UserRole) if current else None)

    def _on_vocab_selected(self, current, _previous):
        self.show_vocab(current.data(Qt.UserRole) if current else None)

    def _set_item_checked(self, item, checked):
        self.vocab_list.blockSignals(True)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.vocab_list.blockSignals(False)

    def _on_vocab_check_toggled(self, item):
        """Checkbox in the vocabulary list: bind or (after confirming) unbind."""
        scheme = item.data(Qt.UserRole)
        checked = item.checkState() == Qt.Checked
        table = self._feature_table()
        if not (self._gpkg and table):
            self._set_item_checked(item, not checked)
            QMessageBox.warning(None, "No Feature Layer",
                "Select a GeoPackage feature layer first.")
            return

        try:
            if checked:
                bind_feature_to_vocab(self._gpkg, table, scheme)
            elif _confirm_unbind(scheme):
                unbind_feature_from_vocab(self._gpkg, table, scheme)
            else:
                self._set_item_checked(item, True)
                return
        except Exception as e:
            self._set_item_checked(item, not checked)
            QMessageBox.critical(None, "Operation Failed",
                f"Could not {'bind' if checked else 'unbind'} vocabulary:\n{e}")
            return

        if self.vocab_list.currentItem() is not item:
            self.vocab_list.setCurrentItem(item)   # -> _on_vocab_selected
        else:
            self.show_vocab(scheme)

    def _on_unbind_clicked(self):
        item = self.vocab_list.currentItem() if self.vocab_list else None
        if item is None:
            QMessageBox.information(None, "Nothing Selected",
                "Select a vocabulary in the list to unbind.")
            return
        if item.checkState() != Qt.Checked:
            return
        # Same path as unticking the checkbox.
        item.setCheckState(Qt.Unchecked)

    # ── Concept tree ───────────────────────────────────────────────────────────

    def _clear_tree(self):
        if self.tree_view:
            self.tree_view.blockSignals(True)
            self.tree_view.clear()
            self.tree_view.blockSignals(False)

    def show_vocab(self, scheme_uri):
        """
        Display the concept tree of scheme_uri for the current feature layer.
        The tree is only shown for vocabularies bound to the layer; concepts
        that already have an annotation field are shown ticked.
        """
        self._shown_scheme = scheme_uri
        self._shown_vocab = None
        self._clear_tree()

        layer = self._layer
        if layer is None:
            self._hint("Select a feature layer.")
            return
        if not scheme_uri:
            self._hint("Import a vocabulary in the Vocabulary tab.")
            return
        if scheme_uri not in self._bound_schemes():
            self._hint("Tick the vocabulary to bind it to this layer.")
            return

        table = find_vocab_table_for_scheme(self._gpkg, scheme_uri)
        try:
            if not table:
                raise LookupError(f"no table registered for {scheme_uri}")
            vocab_layer = ensure_vocab_layer_loaded(self._gpkg, table)
        except Exception as e:
            log(f"Cannot load vocabulary {scheme_uri}: {e}", LEVEL_WARNING)
            self._hint(f"❌ Cannot load vocabulary: {e}")
            return

        self._shown_vocab = vocab_layer
        existing = {f.name() for f in layer.fields()}
        self.tree_view.blockSignals(True)
        try:
            for root in build_concept_tree_items(vocab_layer):
                self.tree_view.addTopLevelItem(root)
            for item in _iter_tree(self.tree_view.invisibleRootItem()):
                if item.data(0, Qt.UserRole) in existing:
                    item.setCheckState(0, Qt.Checked)
        finally:
            self.tree_view.blockSignals(False)
        self._hint(f"Tick a concept to add it as an annotation field to "
                   f"'{layer.name()}'.")

    def _set_tree_item_checked(self, item, checked):
        self.tree_view.blockSignals(True)
        item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
        self.tree_view.blockSignals(False)

    def _on_tree_item_changed(self, item, column):
        if column != 0:
            return
        layer, vocab = self._layer, self._shown_vocab
        if layer is None or vocab is None:
            return
        uri = item.data(0, Qt.UserRole)
        has_field = layer.fields().lookupField(uri) != -1

        if item.checkState(0) == Qt.Checked:
            if not has_field:
                ok = self.create_annotation_field(uri, item.text(0))
                if not ok:
                    self._set_tree_item_checked(item, False)
        elif has_field:
            # Unticking does not delete data; keep the tree truthful.
            self._set_tree_item_checked(item, True)
            QMessageBox.information(None, "Field Kept",
                f"The annotation field '{item.text(0)}' was not removed.\n"
                f"Delete the column via the layer's attribute table if needed.")

    # ── Annotation fields ──────────────────────────────────────────────────────

    def create_annotation_field(self, concept_uri, label):
        """
        Add an annotation field for concept_uri (from the displayed vocabulary)
        to the current feature layer.  Returns True on success.
        """
        layer, vocab = self._layer, self._shown_vocab
        if layer is None or vocab is None:
            return False
        children_map, _ = self.plugin.state.get_hierarchy_for_layer(vocab)
        try:
            result = create_annotation_field(
                layer, vocab, children_map, concept_uri, label
            )
        except RuntimeError as e:
            log(str(e), LEVEL_WARNING)
            QMessageBox.critical(None, "Field Not Created", str(e))
            return False
        if result == "created":
            QMessageBox.information(None, "Field Created",
                f"Annotation field '{label}' created.")
        elif result == "pending":
            QMessageBox.information(None, "Field Added",
                f"Annotation field '{label}' was added to your current edit "
                f"session of '{layer.name()}'. Save your edits to keep it.")
        return True

    def reinitialize_all_annotation_fields_for_layer(self, feature_layer):
        """Re-point the widgets of all annotation fields on a layer."""
        if feature_layer is not None:
            bind_annotation_widgets(
                feature_layer, self.plugin.state.get_hierarchy_for_layer)

    def on_vocabularies_changed(self):
        """A vocabulary was imported/replaced: refresh widgets, list and tree."""
        if self._layer is not None:
            self.reinitialize_all_annotation_fields_for_layer(self._layer)
        self.refresh_vocab_list()

    # ── Layer combo refresh ────────────────────────────────────────────────────

    def refresh_layer_combos(self):
        """
        Restrict the feature layer combo to geometry layers from the active
        GPKG, excluding vocab attribute tables.
        """
        if not self.feature_layer_combo:
            return
        try:
            vocab_tables = set()
            if self._gpkg:
                vocab_tables = {
                    r["layer_name"] for r in read_config(self._gpkg)
                    if r["layer_role"] == ROLE_VOCAB
                }
            excepted = []
            for layer in QgsProject.instance().mapLayers().values():
                if layer.type() != QgsMapLayer.VectorLayer:
                    excepted.append(layer)
                elif layer_table_name(layer) in vocab_tables:
                    excepted.append(layer)
                elif self._gpkg and (
                    norm_path(layer_gpkg_path(layer)) != norm_path(self._gpkg)
                ):
                    excepted.append(layer)
            self.feature_layer_combo.setExceptedLayerList(excepted)
        except RuntimeError:
            pass  # widget already deleted (plugin unloading)
        except Exception as e:
            log(f"refresh_layer_combos error: {e}", LEVEL_WARNING)

    def schedule_refresh(self):
        """Defer refresh to the next event loop tick to avoid reentrancy."""
        if self.plugin.dock_widget:
            QTimer.singleShot(0, self.refresh_layer_combos)
