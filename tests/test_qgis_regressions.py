# test_qgis_regressions.py
# qskos QGIS Plugin - regression tests for bugs reproduced in real QGIS.
#
#   * two vocabularies whose scheme URIs end in the same segment shared one
#     GPKG table: the second import overwrote the first, so the first
#     vocabulary's tree and annotation widget options disappeared
#   * the Layer tab rebuilt itself (hiding the tree) when the layer combo
#     re-emitted the same layer after a filter refresh
#   * annotation fields were text fields: the ValueRelation widget then writes
#     '{"a","b"}', which the symbology's array functions cannot read
#   * ticking a concept while the layer was in edit mode committed the user's
#     unrelated pending edits
#   * a newly imported vocabulary did not appear in the Layer tab
#   * on Windows (GDAL 3.13) vocabulary layers read through QGIS's shared
#     GeoPackage connection returned no rows while a layer of the same file was
#     edited: trees and annotation widgets went empty (ADR-0007)
#   * a layer added to a new project showed annotation widgets without
#     options until the Layer tab was used (vocabulary layer not loaded)
#   * a CSV vocabulary with local concept IDs (no URIs) was stored as is, and
#     the LOD export then failed with 'Invalid line: <C329A7> .'
#
# Run with:  scripts/run_qgis_tests.sh

import pytest

pytest.importorskip("pytest_qgis")

from qgis.core import (
    QgsExpression, QgsExpressionContext, QgsExpressionContextUtils,
    QgsFeatureRequest, QgsField, QgsProject, QgsRuleBasedRenderer,
)
from qgis.gui import QgsGui
from PyQt5.QtCore import Qt, QVariant
from PyQt5.QtWidgets import (
    QApplication, QFileDialog, QInputDialog, QMessageBox, QWidget,
)

from tests.test_qgis_e2e import (  # noqa: F401  (fixtures)
    _annotate_existing_feature, _check_concept, _feat_by_name,
    _find_tree_item, _make_gpkg_feature_layer, _select_vocab, real_iface,
    scenario, SCHEME, SKOS_TTL, ROOT_URI, CHILD_URI,
)
from qskos.utils.fields import parse_field_value
from qskos.utils.gpkg import bind_feature_to_vocab, get_vocab_entries

OTHER_SCHEME = "http://other.example/scheme"   # same last segment as SCHEME
OTHER_ROOT = "http://other.example/o_root"
OTHER_CHILD = "http://other.example/o_child"


def _ttl(scheme, root, child, root_label="Other Root"):
    return f"""@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
<{scheme}> a skos:ConceptScheme .
<{root}> a skos:Concept ; skos:prefLabel "{root_label}"@en ; skos:inScheme <{scheme}> .
<{child}> a skos:Concept ; skos:prefLabel "Other Child"@en ;
    skos:broader <{root}> ; skos:inScheme <{scheme}> .
"""


def _pump():
    for _ in range(5):
        QApplication.processEvents()


def _import(plugin, path, text):
    path.write_text(text, encoding="utf-8")
    plugin.vocabulary_manager.source_input.setText(str(path))
    plugin.vocabulary_manager.on_load_vocab_clicked()
    _pump()


def _widget_options(layer, field_name):
    """Concept URIs the field's ValueRelation widget offers."""
    idx = layer.fields().lookupField(field_name)
    cfg = layer.editorWidgetSetup(idx).config()
    vocab = QgsProject.instance().mapLayer(cfg["Layer"])
    assert vocab is not None and vocab.isValid(), "widget vocab layer unresolved"
    req = QgsFeatureRequest(QgsExpression(cfg["FilterExpression"]))
    return sorted(f["concept"] for f in vocab.getFeatures(req))


def _form_options(layer, field_name, feature):
    """Labels the real attribute form lists for a ValueRelation field — what
    the user sees when annotating a feature."""
    from qgis.gui import QgsAttributeForm, QgsEditorWidgetWrapper
    from PyQt5.QtWidgets import QTableWidget
    form = QgsAttributeForm(layer, feature)
    _pump()
    for w in form.findChildren(QWidget):
        ww = QgsEditorWidgetWrapper.fromWidget(w)
        if ww is not None and ww.field().name() == field_name:
            tables = ww.widget().findChildren(QTableWidget)
            assert tables, f"{type(ww.widget()).__name__} has no option table"
            t = tables[0]
            return sorted(t.item(r, c).text()
                          for r in range(t.rowCount())
                          for c in range(t.columnCount())
                          if t.item(r, c) and t.item(r, c).text())
    raise AssertionError(f"no widget for {field_name} in the form")


def _tree_uris(lm):
    from qskos.tabs.layer import _iter_tree
    return {i.data(0, Qt.UserRole) for i in _iter_tree(lm.tree_view.invisibleRootItem())}


class TestTwoVocabularies:
    def test_same_last_segment_vocabs_stay_separate(self, scenario, tmp_path):
        plugin, layer = scenario.plugin, scenario.layer_a
        plugin.dock_widget.show()
        _import(plugin, tmp_path / "other.ttl",
                _ttl(OTHER_SCHEME, OTHER_ROOT, OTHER_CHILD))
        entries = {e["scheme_uri"]: e["layer_name"] for e in get_vocab_entries(scenario.gpkg)}
        assert entries[SCHEME] != entries[OTHER_SCHEME]

        lm = plugin.layer_manager
        lm.feature_layer_combo.setLayer(layer)
        _pump()
        # Bind the second vocabulary through its list checkbox.
        for i in range(lm.vocab_list.count()):
            if lm.vocab_list.item(i).data(Qt.UserRole) == OTHER_SCHEME:
                lm.vocab_list.item(i).setCheckState(Qt.Checked)
        _pump()

        _check_concept(scenario, layer, ROOT_URI, SCHEME)
        _pump()
        _check_concept(scenario, layer, OTHER_ROOT, OTHER_SCHEME)
        _pump()

        # Switching back shows the first vocabulary's own tree, ticked.
        _select_vocab(plugin, layer, SCHEME)
        _pump()
        assert _tree_uris(lm) == {ROOT_URI, CHILD_URI}
        assert _find_tree_item(lm.tree_view.invisibleRootItem(),
                               ROOT_URI).checkState(0) == Qt.Checked

        # Both fields offer their own vocabulary's concepts.
        assert _widget_options(layer, ROOT_URI) == sorted([ROOT_URI, CHILD_URI])
        assert _widget_options(layer, OTHER_ROOT) == sorted([OTHER_ROOT, OTHER_CHILD])

    def test_import_shows_up_in_layer_tab(self, scenario, tmp_path):
        plugin = scenario.plugin
        lm = _select_vocab(plugin, scenario.layer_a, SCHEME)
        assert lm.vocab_list.count() == 1
        _import(plugin, tmp_path / "other.ttl",
                _ttl(OTHER_SCHEME, OTHER_ROOT, OTHER_CHILD))
        schemes = {lm.vocab_list.item(i).data(Qt.UserRole)
                   for i in range(lm.vocab_list.count())}
        assert schemes == {SCHEME, OTHER_SCHEME}
        # The displayed vocabulary is kept.
        assert lm._shown_scheme == SCHEME
        assert _tree_uris(lm) == {ROOT_URI, CHILD_URI}

    def test_reimport_replaces_concepts_and_keeps_widgets_valid(
            self, scenario, tmp_path, monkeypatch):
        plugin, layer = scenario.plugin, scenario.layer_a
        _check_concept(scenario, layer, ROOT_URI)
        # Answer "Yes" to "replace existing vocabulary?"
        monkeypatch.setattr(QMessageBox, "question",
                            lambda *a, **k: QMessageBox.Yes)
        _import(plugin, tmp_path / "v2.ttl",
                SKOS_TTL.replace('"Root"@en', '"Root v2"@en'))
        lm = plugin.layer_manager
        labels = {lm.tree_view.topLevelItem(i).text(0)
                  for i in range(lm.tree_view.topLevelItemCount())}
        assert labels == {"Root v2"}
        assert _widget_options(layer, ROOT_URI) == sorted([ROOT_URI, CHILD_URI])


class TestLayerTabStability:
    def test_combo_filter_refresh_keeps_tree(self, scenario):
        plugin = scenario.plugin
        plugin.dock_widget.show()
        lm = _select_vocab(plugin, scenario.layer_a, SCHEME)
        assert _tree_uris(lm)
        # Adding layers to the project triggers refresh_layer_combos, which
        # makes QgsMapLayerComboBox re-emit layerChanged for the same layer.
        extra = _make_gpkg_feature_layer(scenario.gpkg, "objects_c", second=True)
        QgsProject.instance().addMapLayer(extra)
        lm.refresh_layer_combos()
        lm.feature_layer_combo.layerChanged.emit(scenario.layer_a)
        _pump()
        assert lm._shown_scheme == SCHEME
        assert _tree_uris(lm) == {ROOT_URI, CHILD_URI}

    def test_unticking_existing_field_keeps_it_ticked(self, scenario):
        _check_concept(scenario, scenario.layer_a, ROOT_URI)
        lm = scenario.plugin.layer_manager
        item = _find_tree_item(lm.tree_view.invisibleRootItem(), ROOT_URI)
        item.setCheckState(0, Qt.Unchecked)
        assert item.checkState(0) == Qt.Checked
        assert scenario.layer_a.fields().lookupField(ROOT_URI) != -1


class TestEditMode:
    def test_ticking_concept_does_not_commit_pending_edits(self, scenario):
        layer = scenario.layer_a
        layer.startEditing()
        feat = _feat_by_name(layer, "obj-objects_a")
        layer.changeAttributeValue(feat.id(), layer.fields().lookupField("name"),
                                   "unsaved")
        _check_concept(scenario, layer, ROOT_URI)

        assert layer.isEditable(), "edit session must stay open"
        assert layer.fields().lookupField(ROOT_URI) != -1
        # Nothing reached the file yet: a fresh reader sees neither change.
        from qgis.core import QgsVectorLayer
        fresh = QgsVectorLayer(f"{scenario.gpkg}|layername=objects_a", "x", "ogr")
        assert fresh.fields().lookupField(ROOT_URI) == -1
        assert _feat_by_name(fresh, "obj-objects_a") is not None

        assert layer.commitChanges(), layer.commitErrors()
        fresh = QgsVectorLayer(f"{scenario.gpkg}|layername=objects_a", "x", "ogr")
        assert fresh.fields().lookupField(ROOT_URI) != -1
        assert _feat_by_name(fresh, "unsaved") is not None


def _rule_matches(layer, rule, feat):
    ctx = QgsExpressionContext()
    ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
    ctx.setFeature(feat)
    exp = QgsExpression(rule.filterExpression())
    result = exp.evaluate(ctx)
    assert not exp.hasEvalError(), exp.evalErrorString()
    return bool(result)


class TestWidgetToSymbology:
    def test_values_written_by_real_widget_drive_symbology(self, scenario):
        """End-to-end through the REAL ValueRelation editor widget: what it
        stores must be readable by parse_field_value and by the rules."""
        plugin, layer = scenario.plugin, scenario.layer_a
        _check_concept(scenario, layer, ROOT_URI)
        idx = layer.fields().lookupField(ROOT_URI)
        assert layer.fields()[idx].type() == QVariant.Map

        setup = layer.editorWidgetSetup(idx)
        parent = QWidget()
        wrapper = QgsGui.editorWidgetRegistry().create(
            setup.type(), layer, idx, setup.config(), None, parent)
        feat = _feat_by_name(layer, "obj-objects_a")
        wrapper.setFeature(feat)
        wrapper.setValues([CHILD_URI], [])
        value = wrapper.value()
        del wrapper
        parent.deleteLater()
        _pump()

        layer.startEditing()
        assert layer.changeAttributeValue(feat.id(), idx, value)
        assert layer.commitChanges()
        feat = _feat_by_name(layer, "obj-objects_a")
        assert parse_field_value(feat[ROOT_URI]) == [CHILD_URI]

        plugin.symbology_manager.generate_rule_based_symbology()
        renderer = layer.renderer()
        assert isinstance(renderer, QgsRuleBasedRenderer)
        group = renderer.rootRule().children()[0]
        assert _rule_matches(layer, group, feat)
        child_rules = {r.label(): r for r in group.children()}
        assert _rule_matches(layer, child_rules["Child"], feat)

    @pytest.mark.parametrize("template", [
        '{{"{root}","{child}"}}',     # ValueRelation widget on a text field
        '["{root}", "{child}"]',      # json.dumps with its ', ' separator
        '{root}|{child}',             # pipe-separated
    ])
    def test_legacy_text_field_values_drive_symbology(self, scenario, template):
        """Annotation fields created as text by older builds hold string
        arrays; symbology must match every value, not just the first."""
        plugin, layer = scenario.plugin, scenario.layer_a
        layer.startEditing()
        layer.addAttribute(QgsField(ROOT_URI, QVariant.String))
        assert layer.commitChanges()
        _annotate_legacy = _feat_by_name(layer, "obj-objects_a")
        layer.startEditing()
        layer.changeAttributeValue(_annotate_legacy.id(),
                                   layer.fields().lookupField(ROOT_URI),
                                   template.format(root=ROOT_URI, child=CHILD_URI))
        assert layer.commitChanges()
        _select_vocab(plugin, layer, SCHEME)

        plugin.symbology_manager.generate_rule_based_symbology()
        group = layer.renderer().rootRule().children()[0]
        feat = _feat_by_name(layer, "obj-objects_a")
        assert _rule_matches(layer, group, feat)
        child_rules = {r.label(): r for r in group.children()}
        assert _rule_matches(layer, child_rules["Child"], feat)   # 2nd value


LOCAL_SCHEME = "https://example.org/local-thesaurus"
LOCAL_CSV = "notation,prefLabel,broader\nB51DAF,Material,\nC329A7,Metall,B51DAF\n"


class TestLocalIdVocabulary:
    @pytest.mark.parametrize("answer", [LOCAL_SCHEME, None])   # None: default
    def test_local_ids_get_scheme_iris_and_export(
            self, scenario, tmp_path, monkeypatch, answer):
        plugin, layer = scenario.plugin, scenario.layer_a
        calls = []
        default = (tmp_path / "local.csv").as_uri()

        def get_text(parent, title, label, text="", *a, **k):
            calls.append(text)
            if len(calls) == 1:
                return "my scheme", True
            return answer or default, True
        monkeypatch.setattr(QInputDialog, "getText", get_text)

        plugin.vocabulary_manager.source_type_combo.setCurrentIndex(1)   # CSV
        _import(plugin, tmp_path / "local.csv", LOCAL_CSV)

        # Suggested default is the file's own URI; a non-URI is asked again,
        # pre-filled with the rejected text so it can be corrected.
        assert calls == [default, "my scheme"]
        scheme = answer or default
        root, child = scheme + "/B51DAF", scheme + "/C329A7"
        table = {e["scheme_uri"]: e["layer_name"]
                 for e in get_vocab_entries(scenario.gpkg)}[scheme]
        import sqlite3
        with sqlite3.connect(scenario.gpkg) as conn:
            rows = set(conn.execute(
                f'SELECT concept, broader, inScheme FROM "{table}"'))
        assert rows == {(root, "", scheme), (child, root, scheme)}

        bind_feature_to_vocab(scenario.gpkg, "objects_a", scheme)
        _check_concept(scenario, layer, root, scheme)
        _pump()
        assert _widget_options(layer, root) == sorted([root, child])
        feat = _feat_by_name(layer, "obj-objects_a")
        assert _form_options(layer, root, feat) == ["Material", "Metall"]
        _annotate_existing_feature(layer, "obj-objects_a", root, [child])

        out = tmp_path / "export.ttl"
        monkeypatch.setattr(QFileDialog, "getSaveFileName",
                            lambda *a, **k: (str(out), "ttl"))
        manager = plugin.lod_export_manager
        manager.refresh_forms()
        manager.forms[0]["id_widget"].setText("O.1")
        manager.title_input.setText("Local IDs")
        manager.on_export_all_clicked()

        from rdflib import Graph, Namespace, URIRef
        g = Graph().parse(str(out), format="turtle")
        assert (None, Namespace("http://www.w3.org/ns/oa#").hasBody,
                URIRef(child)) in g




class TestLayerAddedToProject:
    """The vocabulary layers of a GeoPackage are loaded when one of its
    layers joins the project, not only when the Layer tab is used."""

    def _drop_from_project(self, layer):
        vid = layer.editorWidgetSetup(
            layer.fields().lookupField(ROOT_URI)).config()["Layer"]
        QgsProject.instance().removeMapLayers([vid, layer.id()])
        _pump()

    def test_new_layer_offers_options_without_layer_tab(self, scenario):
        from qgis.core import QgsVectorLayer
        _check_concept(scenario, scenario.layer_a, ROOT_URI)
        _pump()
        self._drop_from_project(scenario.layer_a)

        # As in a new project: add the GeoPackage layer again.
        layer = QgsVectorLayer(f"{scenario.gpkg}|layername=objects_a",
                               "objects_a", "ogr")
        QgsProject.instance().addMapLayer(layer)
        _pump()

        feat = _feat_by_name(layer, "obj-objects_a")
        assert _form_options(layer, ROOT_URI, feat) == ["Child", "Root"]

    def test_unrelated_geopackage_is_not_written(self, scenario, tmp_path):
        import sqlite3
        other = str(tmp_path / "other.gpkg")
        layer = _make_gpkg_feature_layer(other, "roads")
        QgsProject.instance().addMapLayer(layer)
        _pump()
        with sqlite3.connect(other) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        assert not any(t.startswith("qskos") for t in tables)


class TestVocabularyCopies:
    """Trees and widgets read in-memory copies of the vocabulary tables, not
    GeoPackage layers (ADR-0007)."""

    def _vocab_of(self, layer, field_name):
        cfg = layer.editorWidgetSetup(layer.fields().lookupField(field_name)).config()
        return QgsProject.instance().mapLayer(cfg["Layer"])

    def test_widgets_and_tree_read_an_in_memory_copy(self, scenario):
        layer = scenario.layer_a
        _check_concept(scenario, layer, ROOT_URI)
        _pump()
        vocab = self._vocab_of(layer, ROOT_URI)
        assert vocab.providerType() == "memory"
        assert sorted(f["concept"] for f in vocab.getFeatures()) == sorted([ROOT_URI, CHILD_URI])
        assert scenario.plugin.layer_manager._shown_vocab is vocab

    def test_options_survive_unreadable_geopackage_layers(self, scenario):
        """Stand-in for the stale connection: once the plugin has copied the
        vocabulary, GPKG-backed layers of it would read 0 rows."""
        import sqlite3
        layer = scenario.layer_a
        _check_concept(scenario, layer, ROOT_URI)
        _pump()
        with sqlite3.connect(scenario.gpkg) as conn:
            conn.execute(f'ALTER TABLE "{scenario.table}" RENAME TO "{scenario.table}_gone"')
        feat = _feat_by_name(layer, "obj-objects_a")
        assert layer.startEditing()
        assert _form_options(layer, ROOT_URI, feat) == ["Child", "Root"]
        layer.rollBack()

    def test_long_definitions_are_copied(self, scenario, tmp_path, monkeypatch):
        """A bare memory 'string' field holds 255 characters; the provider
        rejected longer definitions, leaving the tree with one concept."""
        plugin, layer = scenario.plugin, scenario.layer_a
        plugin.dock_widget.show()
        monkeypatch.setattr(QInputDialog, "getText",
                            lambda p, t, l, text="", *a, **k: (text, True))
        long_def = "x" * 300
        plugin.vocabulary_manager.source_type_combo.setCurrentIndex(1)   # CSV
        _import(plugin, tmp_path / "long.csv",
                "concept,prefLabel,definition,broader\n"
                f"B51DAF,Material,\"{long_def}\",\n"
                f"C329A7,Metall,\"{long_def}\",B51DAF\n")
        scheme = (tmp_path / "long.csv").as_uri()
        root, child = scheme + "/B51DAF", scheme + "/C329A7"
        bind_feature_to_vocab(scenario.gpkg, "objects_a", scheme)
        lm = _select_vocab(plugin, layer, scheme)
        _pump()
        assert _tree_uris(lm) == {root, child}
        assert lm.tree_view.topLevelItem(0).childCount() == 1
        assert {f["definition"] for f in lm._shown_vocab.getFeatures()} == {long_def}

    def test_saved_project_refills_the_copies(self, scenario, tmp_path):
        _check_concept(scenario, scenario.layer_a, ROOT_URI)
        _pump()
        project = QgsProject.instance()
        path = str(tmp_path / "p.qgz")
        assert project.write(path)
        project.clear()
        _pump()
        assert project.read(path)
        _pump()
        layer = project.mapLayersByName("objects_a")[0]
        vocabs = [l for l in project.mapLayers().values()
                  if l.customProperty("qskos/vocab_source")]
        assert len(vocabs) == 1, [l.name() for l in vocabs]
        feat = _feat_by_name(layer, "obj-objects_a")
        assert _form_options(layer, ROOT_URI, feat) == ["Child", "Root"]

    def test_legacy_geopackage_vocab_layer_is_replaced(self, scenario):
        from qgis.core import QgsVectorLayer
        from qskos.utils.gpkg import INTERNAL_GROUP
        from qskos.utils.layers import ensure_vocab_layer_loaded
        project = QgsProject.instance()
        for l in [l for l in project.mapLayers().values()
                  if l.customProperty("qskos/vocab_source")]:
            project.removeMapLayer(l.id())
        old = QgsVectorLayer(f"{scenario.gpkg}|layername={scenario.table}",
                             scenario.table, "ogr")
        project.addMapLayer(old, False)
        root = project.layerTreeRoot()
        (root.findGroup(INTERNAL_GROUP) or root.insertGroup(0, INTERNAL_GROUP)).addLayer(old)
        old_id = old.id()

        vocab = ensure_vocab_layer_loaded(scenario.gpkg, scenario.table)
        assert vocab.providerType() == "memory"
        assert project.mapLayer(old_id) is None


