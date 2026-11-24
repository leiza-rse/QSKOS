# test_qgis_plugin.py
# qskos QGIS Plugin - QGIS-bound / end-to-end tests.
#
# These run INSIDE a real QGIS Python environment via pytest-qgis (offscreen),
# so they exercise real QgsVectorLayer, real OGR round-tripping and the real
# plugin dock widget. They are NOT run by the plain `uv run pytest` (no QGIS
# runtime): they import pytest_qgis at the top, which is only installed into
# QGIS's own Python (see scripts/install_qgis_ubuntu.sh / run_qgis_tests.sh).
#
# Run with:  scripts/run_qgis_tests.sh
# (which invokes QGIS's python3 -m pytest on this module).

import os
import sys

import pytest

pytest.importorskip("pytest_qgis")

from qgis.core import (
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsFields,
)
from PyQt5.QtCore import QVariant

# The plugin root must be on sys.path. conftest.py normally registers a
# lightweight `qskos` package for pure tests; under real QGIS we want the REAL
# plugin package (with its rdflib purge + PyQt5/QGIS imports), so drop any stub
# and import it fresh.

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PLUGIN_DIR = os.path.join(_ROOT, "qskos")
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

# Remove the lightweight `qskos` stub that tests/conftest.py installed, so the
# real plugin package (qskos/__init__.py) is imported under real QGIS.
sys.modules.pop("qskos", None)
for _name in [m for m in list(sys.modules) if m.startswith("qskos.")]:
    del sys.modules[_name]

import qskos  # real plugin package (noqa: F401) — executes qskos/__init__.py

# Make bundled libs (rdflib etc.) importable, mirroring qskos/__init__.py.
_LIBS_DIR = os.path.join(_PLUGIN_DIR, "libs")
if _LIBS_DIR not in sys.path:
    sys.path.insert(0, _LIBS_DIR)


@pytest.fixture
def real_iface(qgis_app):
    """A minimal real iface so the plugin can construct real widgets on a real
    main window (the default qgis_iface returns MagicMock for mainWindow(),
    which QAction/QDockWidget reject as a parent)."""
    from PyQt5.QtWidgets import QMainWindow, QToolBar

    class _Iface:
        def __init__(self):
            self.win = QMainWindow()
            self.win.resize(800, 600)
            self.toolbar = QToolBar(self.win)
            self.win.addToolBar(self.toolbar)
            self.dock_widgets = []

        def mainWindow(self):
            return self.win

        def addToolBarIcon(self, action):
            self.toolbar.addAction(action)

        def removeToolBarIcon(self, action):
            self.toolbar.removeAction(action)

        def addDockWidget(self, area, dock):
            self.win.addDockWidget(area, dock)
            self.dock_widgets.append(dock)

        def removeDockWidget(self, dock):
            self.win.removeDockWidget(dock)
            if dock in self.dock_widgets:
                self.dock_widgets.remove(dock)

    return _Iface()


@pytest.fixture
def plugin(real_iface, qgis_new_project):
    """Instantiate the real plugin class and wire up its dock widget."""
    from qskos import qskos, classFactory

    inst = classFactory(real_iface)
    inst.initGui()
    yield inst
    try:
        inst.unload()
    except Exception:
        pass


def _make_vocab_layer():
    """Build a real QGIS memory layer with a concept/prefLabel/broader schema
    (two concepts: a root and its child), matching the vocab table shape."""
    layer = QgsVectorLayer("None", "vocab", "memory")
    assert layer.isValid(), "failed to create memory vocab layer"

    provider = layer.dataProvider()
    provider.addAttributes(
        [
            QgsField("concept", QVariant.String),
            QgsField("prefLabel", QVariant.String),
            QgsField("broader", QVariant.String),
        ]
    )
    layer.updateFields()
    fields = layer.fields()

    f1 = QgsFeature(fields)
    f1.setAttribute("concept", "http://root")
    f1.setAttribute("prefLabel", "Root")
    f1.setAttribute("broader", None)
    f2 = QgsFeature(fields)
    f2.setAttribute("concept", "http://child")
    f2.setAttribute("prefLabel", "Child")
    f2.setAttribute("broader", "http://root")

    assert provider.addFeatures([f1, f2])
    return layer


def _make_feature_layer():
    """Build a real QGIS point memory layer (what you'd annotate)."""
    layer = QgsVectorLayer("Point?crs=EPSG:4326", "features", "memory")
    assert layer.isValid(), "failed to create memory feature layer"
    return layer


class TestPluginBoot:
    def test_class_factory_and_dock_build(self, plugin):
        """The plugin must instantiate and build its dock with all five tabs."""
        assert plugin.dock_widget is not None
        assert plugin.tab_widget is not None
        assert plugin.tab_widget.count() == 5

    def test_state_object_injected(self, plugin):
        from qskos.state import QskosState
        assert isinstance(plugin.state, QskosState)


class TestAnnotationFieldOnRealLayers:
    def test_create_annotation_field_roundtrips(self, qgis_new_project):
        """Create a ValueRelation annotation field on a real layer and verify it."""
        from qskos.utils.annotation import create_annotation_field
        from qskos.utils.hierarchy import build_hierarchy_index

        vocab_layer = _make_vocab_layer()
        feature_layer = _make_feature_layer()

        children_map, concept_labels = build_hierarchy_index(vocab_layer)

        created = create_annotation_field(
            feature_layer, vocab_layer, children_map, "http://child", "Child"
        )
        assert created == "created"

        # Re-creating the same field must be a no-op.
        again = create_annotation_field(
            feature_layer, vocab_layer, children_map, "http://child", "Child"
        )
        assert again == "exists"

        # Field must exist with the right editor widget type.
        idx = feature_layer.fields().lookupField("http://child")
        assert idx != -1
        setup = feature_layer.editorWidgetSetup(idx)
        assert setup.type() == "ValueRelation"

    def test_value_relation_config_filter_targets_concept_and_descendants(self):
        """The config filter must list the concept itself plus its descendants
        (regression: a leaf concept must still offer itself as a value)."""
        from qskos.utils.annotation import build_value_relation_config
        from qskos.utils.hierarchy import build_hierarchy_index

        vocab_layer = _make_vocab_layer()
        children_map, _ = build_hierarchy_index(vocab_layer)
        config = build_value_relation_config(
            vocab_layer.id(), children_map, "http://root"
        )
        assert config["Layer"] == vocab_layer.id()
        assert config["AllowMulti"] is True
        # root plus its child must both be offered
        assert "http://child" in config["FilterExpression"]
        assert "http://root" in config["FilterExpression"]

    def test_leaf_concept_still_offers_a_value(self):
        """A concept with no descendants must still yield a usable filter
        (itself), not the degenerate '0' that produced no checkboxes."""
        from qskos.utils.annotation import build_value_relation_config
        from qskos.utils.hierarchy import build_hierarchy_index

        vocab_layer = _make_vocab_layer()
        children_map, _ = build_hierarchy_index(vocab_layer)
        config = build_value_relation_config(
            vocab_layer.id(), children_map, "http://child"
        )
        # not the empty/degenerate filter
        assert config["FilterExpression"] != "0"
        assert "http://child" in config["FilterExpression"]


class TestMultiLayerBinding:
    """Regression guard for assessment item M: two feature layers bound to the
    same vocabulary must not clobber each other's state."""

    def test_annotation_fields_created_independently(self, qgis_new_project):
        from qskos.utils.annotation import create_annotation_field
        from qskos.utils.hierarchy import build_hierarchy_index

        vocab_layer = _make_vocab_layer()
        layer_a = _make_feature_layer()
        layer_b = _make_feature_layer()

        children_map, _ = build_hierarchy_index(vocab_layer)

        create_annotation_field(layer_a, vocab_layer, children_map, "http://root", "Root")
        create_annotation_field(layer_b, vocab_layer, children_map, "http://root", "Root")

        assert layer_a.fields().lookupField("http://root") != -1
        assert layer_b.fields().lookupField("http://root") != -1

        # Each layer's ValueRelation points at the shared vocab, but the two
        # layers must remain independent (this is what the old globals broke).
        a_cfg = layer_a.editorWidgetSetup(layer_a.fields().lookupField("http://root"))
        b_cfg = layer_b.editorWidgetSetup(layer_b.fields().lookupField("http://root"))
        assert a_cfg.type() == "ValueRelation"
        assert b_cfg.type() == "ValueRelation"
