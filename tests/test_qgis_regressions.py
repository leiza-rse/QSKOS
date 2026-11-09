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
from PyQt5.QtWidgets import QApplication, QMessageBox, QWidget

from tests.test_qgis_e2e import (  # noqa: F401  (fixtures)
    _annotate_existing_feature, _check_concept, _feat_by_name,
    _find_tree_item, _make_gpkg_feature_layer, _select_vocab, real_iface,
    scenario, SCHEME, SKOS_TTL, ROOT_URI, CHILD_URI,
)
from qskos.utils.fields import parse_field_value
from qskos.utils.gpkg import get_vocab_entries

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

    def test_legacy_text_field_values_drive_symbology(self, scenario):
        """Fields created as text by the 2026-10 refactor builds hold
        '{"a","b"}'; symbology must still match them."""
        plugin, layer = scenario.plugin, scenario.layer_a
        layer.startEditing()
        layer.addAttribute(QgsField(ROOT_URI, QVariant.String))
        assert layer.commitChanges()
        _annotate_legacy = _feat_by_name(layer, "obj-objects_a")
        layer.startEditing()
        layer.changeAttributeValue(_annotate_legacy.id(),
                                   layer.fields().lookupField(ROOT_URI),
                                   f'{{"{CHILD_URI}"}}')
        assert layer.commitChanges()
        _select_vocab(plugin, layer, SCHEME)

        plugin.symbology_manager.generate_rule_based_symbology()
        group = layer.renderer().rootRule().children()[0]
        assert _rule_matches(layer, group, _feat_by_name(layer, "obj-objects_a"))
