# __init__.py
# qskos QGIS Plugin - Main Plugin Class
# Initialises the dock widget, wires all tabs, manages cross-tab state.

import os

from PyQt5.QtWidgets import QAction, QDockWidget, QTabWidget
from PyQt5.QtCore import Qt, QTimer
from qgis.core import QgsProject

from .tabs.geopackage import GeopackageManager
from .tabs.vocabulary import VocabularyManager
from .tabs.layer import LayerManager
from .tabs.symbology import SymbologyManager
from .utils.hierarchy import build_hierarchy_index


class qskos:
    def __init__(self, iface):
        self.iface      = iface
        self.plugin_dir = os.path.dirname(__file__)

        # ── Cross-tab state ────────────────────────────────────────────────────
        self.active_gpkg_path      = None   # Path to the active GeoPackage
        self.current_feature_layer = None   # Feature layer selected in Layer tab
        self.current_vocab_layer   = None   # Vocab layer currently shown in tree
        self.current_vocab_scheme  = None   # scheme_uri of current tree vocab
        self.selected_language     = "en"   # Import language
        self.hierarchy_cache       = {}     # vocab_layer.id() → (children_map, labels)

        # ── Widget references ──────────────────────────────────────────────────
        self.dock_widget = None
        self.tab_widget  = None

        # ── Tab managers ───────────────────────────────────────────────────────
        self.geopackage_manager = GeopackageManager(self)
        self.vocabulary_manager = VocabularyManager(self)
        self.layer_manager      = LayerManager(self)
        self.symbology_manager  = SymbologyManager(self)

    # ── Hierarchy cache ────────────────────────────────────────────────────────

    def get_hierarchy_for_layer(self, vocab_layer):
        """
        Return (children_map, concept_labels) for vocab_layer, building and
        caching on first call.  Cache is keyed by layer.id() — safe for
        saved/reopened projects because layer IDs change on reload, triggering
        an automatic rebuild.
        """
        layer_id = vocab_layer.id()
        if layer_id not in self.hierarchy_cache:
            self.hierarchy_cache[layer_id] = build_hierarchy_index(vocab_layer)
            print(f"[qskos] Built hierarchy cache for: {vocab_layer.name()}")
        return self.hierarchy_cache[layer_id]

    # ── QGIS plugin lifecycle ──────────────────────────────────────────────────

    def initGui(self):
        """Create toolbar icon, build dock widget with four tabs."""
        self.action = QAction("qskos", self.iface.mainWindow())
        self.action.triggered.connect(self.toggle_dock_widget)
        self.iface.addToolBarIcon(self.action)

        self.dock_widget = QDockWidget(
            "qskos Semantic Annotation", self.iface.mainWindow()
        )
        self.dock_widget.setObjectName("qskosDockWidget")

        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(
            self.geopackage_manager.setup_geopackage_tab(), "GeoPackage"
        )
        self.tab_widget.addTab(
            self.vocabulary_manager.setup_vocab_tab(), "Vocabulary"
        )
        self.tab_widget.addTab(
            self.layer_manager.setup_layer_tab(), "Layer"
        )
        self.tab_widget.addTab(
            self.symbology_manager.setup_symbology_tab(), "Symbology"
        )

        self.dock_widget.setWidget(self.tab_widget)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)
        self.dock_widget.hide()

        project = QgsProject.instance()
        project.layerWasAdded.connect(self.schedule_refresh)
        project.layerWillBeRemoved.connect(self.schedule_refresh)
        project.readProject.connect(self._restore_gpkg_path)
        project.writeProject.connect(self._save_gpkg_path)

    def unload(self):
        """Remove plugin UI and disconnect all signals."""
        project = QgsProject.instance()
        for sig, slot in (
            (project.layerWasAdded,        self.schedule_refresh),
            (project.layerWillBeRemoved,   self.schedule_refresh),
            (project.readProject,          self._restore_gpkg_path),
            (project.writeProject,         self._save_gpkg_path),
        ):
            try:
                sig.disconnect(slot)
            except TypeError:
                pass

        if hasattr(self, "action"):
            self.iface.removeToolBarIcon(self.action)
        if self.dock_widget:
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget.deleteLater()
            self.dock_widget = None

    def run(self):
        """Legacy entry point — delegates to toggle."""
        self.toggle_dock_widget()

    def toggle_dock_widget(self):
        if self.dock_widget:
            if self.dock_widget.isVisible():
                self.dock_widget.hide()
            else:
                self.dock_widget.show()
                self.layer_manager.refresh_layer_combos()

    # ── Project persistence ────────────────────────────────────────────────────

    def _save_gpkg_path(self):
        """Write the active GPKG path into the QGIS project file."""
        if self.active_gpkg_path:
            QgsProject.instance().writeEntry(
                "qskos", "active_gpkg", self.active_gpkg_path
            )

    def _restore_gpkg_path(self):
        """
        Restore the active GPKG path from the QGIS project file on project open.
        Calls load_gpkg() so all tabs are refreshed as if the user had selected it.
        """
        path, ok = QgsProject.instance().readEntry("qskos", "active_gpkg", "")
        if ok and path and os.path.exists(path):
            self.geopackage_manager.load_gpkg(path)

    # ── Signal dispatch to managers ───────────────────────────────────────────

    def schedule_refresh(self):
        """Defer a layer combo refresh to the next event loop tick."""
        if self.dock_widget:
            QTimer.singleShot(0, self.layer_manager.refresh_layer_combos)

    def on_feature_layer_changed(self, layer):
        self.layer_manager.on_feature_layer_changed(layer)

    def on_tree_item_changed(self, item, column):
        """
        Checking a concept node creates an annotation field on the feature layer.
        Unchecking does nothing — annotation columns must be removed manually
        via the layer attribute table.
        """
        if column != 0:
            return
        if item.checkState(0) == Qt.Checked:
            self.layer_manager.create_annotation_field(
                item.data(0, Qt.UserRole), item.text(0)
            )
        # Qt.Unchecked: intentionally no action


# REQUIRED ENTRY POINT FOR QGIS — DO NOT REMOVE!
def classFactory(iface):
    return qskos(iface)