# __init__.py
# qskos QGIS Plugin - Main Plugin Class
# Initialises the dock widget, wires all tabs, manages cross-tab state.

import os
import sys

# Make bundled pure-Python dependencies (e.g. rdflib) importable.
# These live in the plugin's libs/ folder so users don't need pip.
_PLUGIN_DIR = os.path.dirname(__file__)
_LIBS_DIR = os.path.join(_PLUGIN_DIR, "libs")
if os.path.isdir(_LIBS_DIR) and _LIBS_DIR not in sys.path:
    sys.path.insert(0, _LIBS_DIR)

# QGIS ships its own (often older/incomplete) rdflib in its Python
# environment and may import it before this plugin loads.  Once rdflib is in
# sys.modules the sys.path insert above is ignored, so the plugin would use
# QGIS's rdflib and fail with e.g. "No module named
# 'rdflib.plugins.stores.memory'".  Force our bundled copy to win by purging
# any pre-imported rdflib modules before anything imports them.
for _mod in list(sys.modules):
    if _mod == "rdflib" or _mod.startswith("rdflib."):
        del sys.modules[_mod]
del _mod

from PyQt5.QtWidgets import QAction, QDockWidget, QTabWidget
from PyQt5.QtCore import Qt, QTimer
from qgis.core import QgsProject

from .tabs.geopackage import GeopackageManager
from .tabs.vocabulary import VocabularyManager
from .tabs.layer import LayerManager
from .tabs.symbology import SymbologyManager
from .tabs.lod_export import LODExportManager
from .state import QskosState


class qskos:
    def __init__(self, iface):
        self.iface      = iface
        self.plugin_dir = os.path.dirname(__file__)

        # ── Cross-tab state (typed, explicit; see state.py) ────────────────────
        self.state = QskosState()

        # ── Widget references ──────────────────────────────────────────────────
        self.dock_widget = None
        self.tab_widget  = None

        # ── Tab managers ───────────────────────────────────────────────────────
        self.geopackage_manager = GeopackageManager(self)
        self.vocabulary_manager = VocabularyManager(self)
        self.layer_manager      = LayerManager(self)
        self.symbology_manager  = SymbologyManager(self)
        self.lod_export_manager = LODExportManager(self)

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
        self.tab_widget.addTab(
            self.lod_export_manager.setup_lod_tab(), "LOD Export"
        )

        # Rebuild the per-layer LOD export forms when that tab is shown
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

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
        if self.state.active_gpkg_path:
            QgsProject.instance().writeEntry(
                "qskos", "active_gpkg", self.state.active_gpkg_path
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

    def _on_tab_changed(self, index):
        """Refresh the LOD export forms whenever that tab is shown."""
        if self.tab_widget and self.tab_widget.widget(index) is \
                self.lod_export_manager.tab_widget:
            self.lod_export_manager.refresh_forms()

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