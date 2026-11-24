# test_qgis_e2e.py
# qskos QGIS Plugin - full end-to-end scenario tests.
#
# Mirrors the manual acceptance workflow against REAL QGIS objects:
#   tab 1  select GeoPackage (load_gpkg)
#   tab 2  import vocabulary (real on_load_vocab_clicked flow, local file;
#          remote URLs need network and are not automatable in CI)
#   tab 3  bind layer to vocab, tick concepts in the tree (real signal wiring)
#   edit   annotate existing features, edit values — guards the prior
#          "editing deletes attribute values" bug (assessment item M family)
#   tab 4  generate symbology, export LOD via the real export-all flow
#
# Run with:  scripts/run_qgis_tests.sh  (headless, pytest-qgis)

import os
import sys
import tempfile
from types import SimpleNamespace

import pytest

pytest.importorskip("pytest_qgis")

from qgis.core import (
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRuleBasedRenderer,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from PyQt5.QtCore import Qt, QVariant
from PyQt5.QtWidgets import QFileDialog, QMessageBox

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PLUGIN_DIR = os.path.join(_ROOT, "qskos")
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

import qskos as _q

if not hasattr(_q, "classFactory"):
    # conftest.py installed a lightweight `qskos` stub for the pure tests —
    # replace it with the real plugin package under real QGIS.
    sys.modules.pop("qskos", None)
    for _name in [m for m in list(sys.modules) if m.startswith("qskos.")]:
        del sys.modules[_name]
    import qskos as _q

_LIBS_DIR = os.path.join(_PLUGIN_DIR, "libs")
if _LIBS_DIR not in sys.path:
    sys.path.insert(0, _LIBS_DIR)

from qskos.utils.fields import parse_field_value
from qskos.utils.gpkg import (
    bind_feature_to_vocab,
    get_vocab_entries,
    ROLE_VOCAB,
)
from qskos.utils.layers import ensure_vocab_layer_loaded

SCHEME = "http://vocab.example/scheme"
ROOT_URI = "http://vocab.example/root"
CHILD_URI = "http://vocab.example/child"

# Controlled two-concept vocabulary written through the real tab-2 import flow.
SKOS_TTL = """@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

<http://vocab.example/scheme> a skos:ConceptScheme ;
    skos:prefLabel "Test Scheme"@en .

<http://vocab.example/root> a skos:Concept ;
    skos:prefLabel "Root"@en ;
    skos:inScheme <http://vocab.example/scheme> .

<http://vocab.example/child> a skos:Concept ;
    skos:prefLabel "Child"@en ;
    skos:broader <http://vocab.example/root> ;
    skos:inScheme <http://vocab.example/scheme> .
"""


def _silence_dialogs(monkeypatch):
    """Modal dialogs would block headless runs — stub them out."""
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: QMessageBox.Ok)
    # Decline any "replace scheme?" prompt (fresh GPKG per test → not expected).
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)


def _make_gpkg_feature_layer(gpkg, layer_name, second=False):
    """Create a REAL GeoPackage-backed point layer with one feature."""
    mem = QgsVectorLayer("Point?crs=EPSG:4326", layer_name, "memory")
    assert mem.isValid(), "memory layer invalid"
    mem.dataProvider().addAttributes([QgsField("name", QVariant.String)])
    mem.updateFields()

    f = QgsFeature(mem.fields())
    f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(8.0, 49.0)))
    f.setAttribute("name", f"obj-{layer_name}")
    assert mem.dataProvider().addFeatures([f])

    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = layer_name
    opts.fileEncoding = "UTF-8"
    if second:
        opts.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
    result = QgsVectorFileWriter.writeAsVectorFormatV3(
        mem, gpkg, QgsCoordinateTransformContext(), opts
    )
    err = result[0] if isinstance(result, tuple) else result
    assert err == QgsVectorFileWriter.NoError, f"GPKG write failed: {err}"

    layer = QgsVectorLayer(f"{gpkg}|layername={layer_name}", layer_name, "ogr")
    assert layer.isValid(), f"GPKG layer {layer_name} invalid"
    return layer


def _feat_by_name(layer, name):
    for f in layer.getFeatures():
        if f["name"] == name:
            return f
    return None


def _feat_by_fid(layer, fid):
    for f in layer.getFeatures():
        if f.id() == fid:
            return f
    return None


def _find_tree_item(parent, uri):
    for i in range(parent.childCount()):
        child = parent.child(i)
        if child.data(0, Qt.UserRole) == uri:
            return child
        found = _find_tree_item(child, uri)
        if found:
            return found
    return None


def _select_vocab(plugin, layer, scheme_uri):
    """Pick the feature layer in the combo and the vocabulary in the list,
    like a user would; returns the LayerManager."""
    lm = plugin.layer_manager
    lm.feature_layer_combo.setLayer(layer)
    lm.refresh_vocab_list()   # bindings may have been written outside the UI
    for i in range(lm.vocab_list.count()):
        if lm.vocab_list.item(i).data(Qt.UserRole) == scheme_uri:
            lm.vocab_list.setCurrentRow(i)
    assert lm._shown_scheme == scheme_uri
    return lm


def _check_concept(scenario, layer, uri, scheme_uri=None):
    """Tick a concept in the tree like a user would — via the real signals:
    combo -> vocab list -> tree checkbox -> itemChanged -> field creation."""
    lm = _select_vocab(scenario.plugin, layer, scheme_uri or scenario.scheme_uri)
    item = _find_tree_item(lm.tree_view.invisibleRootItem(), uri)
    assert item is not None, f"concept {uri} not found in tree"
    item.setCheckState(0, Qt.Checked)


def _annotate_existing_feature(layer, name, uri, value):
    """Set an annotation value on an existing feature, as the ValueRelation
    editor widget does for a JSON field (a list of concept URIs)."""
    feat = _feat_by_name(layer, name)
    assert feat is not None, f"feature {name} not found"
    idx = layer.fields().lookupField(uri)
    assert idx != -1
    layer.startEditing()
    assert layer.changeAttributeValue(feat.id(), idx, list(value))
    assert layer.commitChanges()


@pytest.fixture
def real_iface(qgis_app):
    """Minimal real iface: real widgets on a real main window, plus the
    layerTreeView hook symbology/reset call."""
    from PyQt5.QtWidgets import QMainWindow, QToolBar

    class _LayerTreeView:
        def refreshLayerSymbology(self, layer_id):
            pass

    class _Iface:
        def __init__(self):
            self.win = QMainWindow()
            self.win.resize(800, 600)
            self.toolbar = QToolBar(self.win)
            self.win.addToolBar(self.toolbar)
            self.dock_widgets = []

        def mainWindow(self):
            return self.win

        def layerTreeView(self):
            return _LayerTreeView()

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
def scenario(monkeypatch, qgis_new_project, real_iface, tmp_path):
    """Full setup: real GPKG with two feature layers, vocab imported through
    the real tab-2 flow, both layers bound (tab 3)."""
    _silence_dialogs(monkeypatch)
    tmp = tempfile.TemporaryDirectory(prefix="qskos-e2e-")
    try:
        plugin = _q.classFactory(real_iface)
        plugin.initGui()
        gpkg = os.path.join(tmp.name, "project.gpkg")

        # Real GeoPackage-backed feature layers (same GPKG, two tables)
        layer_a = _make_gpkg_feature_layer(gpkg, "objects_a")
        layer_b = _make_gpkg_feature_layer(gpkg, "objects_b", second=True)
        QgsProject.instance().addMapLayer(layer_a)
        QgsProject.instance().addMapLayer(layer_b)

        # Tab 1: select the GeoPackage (real load_gpkg flow)
        plugin.geopackage_manager.load_gpkg(gpkg)
        assert plugin.state.active_gpkg_path == gpkg

        # Tab 2: import the controlled vocab through the real callback
        ttl_path = tmp_path / "vocab.ttl"
        ttl_path.write_text(SKOS_TTL, encoding="utf-8")
        vm = plugin.vocabulary_manager
        vm.source_input.setText(str(ttl_path))
        vm.on_load_vocab_clicked()

        entries = get_vocab_entries(gpkg)
        assert len(entries) == 1, f"expected 1 vocab, got {entries}"
        scheme_uri = entries[0]["scheme_uri"]
        table = entries[0]["layer_name"]

        # Tab 3: bind both feature layers to the vocabulary (checkbox equivalent)
        bind_feature_to_vocab(gpkg, "objects_a", scheme_uri)
        bind_feature_to_vocab(gpkg, "objects_b", scheme_uri)

        yield SimpleNamespace(
            plugin=plugin,
            gpkg=gpkg,
            table=table,
            scheme_uri=scheme_uri,
            layer_a=layer_a,
            layer_b=layer_b,
        )
        plugin.unload()
    finally:
        tmp.cleanup()


def _vocab_layer(scenario):
    return ensure_vocab_layer_loaded(scenario.gpkg, scenario.table)


class TestVocabImport:
    def test_import_via_real_tab_flow(self, scenario):
        """The fixture imports through on_load_vocab_clicked — verify results."""
        entries = get_vocab_entries(scenario.gpkg)
        assert len(entries) == 1
        assert entries[0]["layer_role"] == ROLE_VOCAB
        assert entries[0]["language"] == "en"

        # The vocab table must load as a real OGR layer (tab-2 does this too).
        vl = _vocab_layer(scenario)
        assert vl.isValid()
        uris = {f["concept"] for f in vl.getFeatures()}
        assert {ROOT_URI, CHILD_URI} <= uris

    def test_local_import_of_shipped_thesaurus(self, scenario):
        """Import the real bundled thesaurus (local file, German labels)."""
        plugin = scenario.plugin
        ttl = os.path.join(_PLUGIN_DIR, "Konservierungsthesaurus.ttl")
        plugin.vocabulary_manager.language_combo.setCurrentText("de")
        assert plugin.state.selected_language == "de"
        plugin.vocabulary_manager.source_input.setText(ttl)
        plugin.vocabulary_manager.on_load_vocab_clicked()

        entries = get_vocab_entries(scenario.gpkg)
        assert len(entries) == 2
        thesaurus = [
            e for e in entries if "conservationthesaurus" in e["scheme_uri"]
        ]
        assert thesaurus, "shipped thesaurus not registered"
        vl = ensure_vocab_layer_loaded(scenario.gpkg, thesaurus[0]["layer_name"])
        labels = [f["prefLabel"] for f in vl.getFeatures()]
        assert any(labels), "no prefLabels imported"


class TestAnnotationWorkflow:
    def test_tree_check_creates_annotation_field(self, scenario):
        """Ticking a concept in the tree (real signal wiring) creates the field."""
        plugin = scenario.plugin
        _check_concept(scenario, scenario.layer_a, CHILD_URI)

        assert scenario.layer_a.fields().lookupField(CHILD_URI) != -1
        setup = scenario.layer_a.editorWidgetSetup(
            scenario.layer_a.fields().lookupField(CHILD_URI)
        )
        assert setup.type() == "ValueRelation"

    def test_editing_features_preserves_annotation_values(self, scenario):
        """Regression guard: editing feature values must never delete stored
        annotation values (the pre-refactor bug)."""
        plugin = scenario.plugin
        _check_concept(scenario, scenario.layer_a, CHILD_URI)

        layer = scenario.layer_a
        name_idx = layer.fields().lookupField("name")
        idx = layer.fields().lookupField(CHILD_URI)

        # Annotate the EXISTING feature created by the GPKG writer.
        _annotate_existing_feature(
            layer, "obj-objects_a", CHILD_URI, [CHILD_URI]
        )
        fid = _feat_by_name(layer, "obj-objects_a").id()
        assert parse_field_value(
            _feat_by_name(layer, "obj-objects_a")[CHILD_URI]
        ) == [CHILD_URI]

        # Edit the other (non-annotation) attribute → annotation must survive.
        layer.startEditing()
        assert layer.changeAttributeValue(fid, name_idx, "renamed")
        assert layer.commitChanges()
        feat = _feat_by_fid(layer, fid)
        assert feat["name"] == "renamed"
        assert parse_field_value(feat[CHILD_URI]) == [CHILD_URI]

        # Re-edit the annotation value itself (ValueRelation re-pick).
        layer.startEditing()
        assert layer.changeAttributeValue(
            fid, idx, [CHILD_URI, ROOT_URI]
        )
        assert layer.commitChanges()
        feat = _feat_by_fid(layer, fid)
        assert parse_field_value(feat[CHILD_URI]) == [CHILD_URI, ROOT_URI]

        # Deep round-trip: a fresh layer from disk (project-reload equivalent).
        fresh = QgsVectorLayer(
            f"{scenario.gpkg}|layername=objects_a", "objects_a", "ogr"
        )
        assert fresh.isValid()
        feat = _feat_by_fid(fresh, fid)
        assert feat["name"] == "renamed"
        assert parse_field_value(feat[CHILD_URI]) == [CHILD_URI, ROOT_URI]

    def test_second_layer_binding_is_independent(self, scenario):
        """Two feature layers bound to the same vocab must not clobber each
        other (assessment item M)."""
        plugin = scenario.plugin

        # Annotate one existing feature on each layer.
        for lyr in (scenario.layer_a, scenario.layer_b):
            _check_concept(scenario, lyr, CHILD_URI)
            _annotate_existing_feature(
                lyr, f"obj-{lyr.name()}", CHILD_URI, [CHILD_URI]
            )

        # Edit layer A's annotation value.
        _annotate_existing_feature(
            scenario.layer_a, "obj-objects_a", CHILD_URI, [CHILD_URI, ROOT_URI]
        )

        # Layer B's stored value must be untouched.
        feat_b = _feat_by_name(scenario.layer_b, "obj-objects_b")
        assert parse_field_value(feat_b[CHILD_URI]) == [CHILD_URI]

    def test_third_layer_binding_keeps_first_layer_bound(self, scenario):
        """Binding the same vocabulary to additional layers must never drop the
        first layer's binding (regression for the reported 'first layer was
        gone' symptom). Drives the REAL UI path: combo selection + the vocab
        checkbox toggle that fires _on_vocab_check_toggled."""
        plugin = scenario.plugin
        lm = plugin.layer_manager

        from qskos.utils.gpkg import get_bound_vocab_schemes
        from PyQt5.QtCore import Qt

        # Create a third feature layer in the same GPKG (extends it, not overwrite).
        layer_c = _make_gpkg_feature_layer(
            scenario.gpkg, "objects_c", second=True
        )
        QgsProject.instance().addMapLayer(layer_c)

        def bind_current_layer_via_checkbox():
            # Auto-selected first vocab item; toggle its checkbox -> itemChanged
            # -> _on_vocab_check_toggled (real signal path).
            item = lm.vocab_list.item(0)
            item.setCheckState(Qt.Checked)

        # Bind all three layers through the real combo + checkbox path.
        for lyr in (scenario.layer_a, scenario.layer_b, layer_c):
            lm.feature_layer_combo.setLayer(lyr)
            bind_current_layer_via_checkbox()
            assert get_bound_vocab_schemes(
                scenario.gpkg, lyr.name()
            ) == [scenario.scheme_uri], f"{lyr.name()} not bound"

        # Every layer must still be bound, including the very first.
        assert get_bound_vocab_schemes(
            scenario.gpkg, "objects_a"
        ) == [scenario.scheme_uri]

        # Switching back to the first layer must still show it bound.
        lm.feature_layer_combo.setLayer(scenario.layer_a)
        assert lm.vocab_list.count() > 0
        assert lm.vocab_list.item(0).checkState() == Qt.Checked


class TestSymbologyAndExport:
    def test_symbology_generation_on_real_layer(self, scenario):
        plugin = scenario.plugin
        _check_concept(scenario, scenario.layer_a, ROOT_URI)
        _annotate_existing_feature(
            scenario.layer_a, "obj-objects_a", ROOT_URI, [CHILD_URI]
        )

        plugin.symbology_manager.generate_rule_based_symbology()

        renderer = scenario.layer_a.renderer()
        assert isinstance(renderer, QgsRuleBasedRenderer)
        children = renderer.rootRule().children()
        assert children, "expected generated rules"
        filters = [c.filterExpression() for c in children]
        assert any("array_intersect" in f for f in filters)

    def test_lod_export_produces_valid_turtle(self, scenario, tmp_path, monkeypatch):
        plugin = scenario.plugin
        _check_concept(scenario, scenario.layer_a, CHILD_URI)
        _annotate_existing_feature(
            scenario.layer_a, "obj-objects_a", CHILD_URI, [CHILD_URI]
        )

        out = tmp_path / "export.ttl"
        monkeypatch.setattr(
            QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), "ttl")
        )

        manager = plugin.lod_export_manager
        manager.refresh_forms()
        assert len(manager.forms) == 1, "only objects_a has annotation fields"
        manager.forms[0]["id_widget"].setText("O.1")
        manager.forms[0]["label_widget"].setText("Test Object")
        manager.title_input.setText("E2E export")   # required DCAT title
        manager.on_export_all_clicked()

        assert out.exists() and out.stat().st_size > 0

        from rdflib import Graph, Namespace, URIRef

        OA = Namespace("http://www.w3.org/ns/oa#")
        QSKOS = Namespace("http://archaeology.link/ontology/qskos#")
        g = Graph()
        g.parse(str(out), format="turtle")
        assert len(g) > 0
        # One annotation: field concept as qskos:attribute, the selected value
        # as oa:hasBody, the feature as oa:hasTarget (rdf_model.py).
        anns = list(g.subjects(QSKOS.attribute, URIRef(CHILD_URI)))
        assert len(anns) == 1
        assert (anns[0], OA.hasBody, URIRef(CHILD_URI)) in g
        assert (anns[0], OA.hasTarget, None) in g
        assert (None, QSKOS.usesVocabulary, URIRef(scenario.scheme_uri)) in g
