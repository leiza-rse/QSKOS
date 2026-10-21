# test_state.py
# qskos QGIS Plugin - unit tests for the shared QskosState object (state.py).
# Verifies that the typed cross-tab state replaces the old ad-hoc plugin
# globals and that the hierarchy cache is keyed per layer.

from qskos.state import QskosState


class FakeVocabLayer:
    """Minimal stand-in for a QGIS vocab layer: source() + getFeatures()."""

    def __init__(self, source, features):
        self._source = source
        self._features = features

    def source(self):
        return self._source

    def getFeatures(self):
        return iter(self._features)


def _features(rows):
    return [
        {"concept": uri, "broader": broader, "prefLabel": label}
        for uri, broader, label in rows
    ]


def test_defaults():
    s = QskosState()
    assert s.active_gpkg_path is None
    assert s.current_feature_layer is None
    assert s.current_vocab_layer is None
    assert s.current_vocab_scheme is None
    assert s.selected_language == "en"
    assert s.hierarchy_cache == {}


def test_state_is_typed_and_independent():
    # Two states must not share cache (each manager can hold its own).
    a = QskosState()
    b = QskosState()
    assert a.hierarchy_cache is not b.hierarchy_cache
    a.active_gpkg_path = "/tmp/x.gpkg"
    assert b.active_gpkg_path is None


def test_get_hierarchy_builds_and_caches():
    layer = FakeVocabLayer("/tmp/x.gpkg|layername=vocab", _features([
        ("http://root", None, "Root"),
        ("http://child", "http://root", "Child"),
    ]))
    s = QskosState()
    children, labels = s.get_hierarchy_for_layer(layer)
    assert labels == {"http://root": "Root", "http://child": "Child"}
    assert children[None] == ["http://root"]
    assert children["http://root"] == ["http://child"]
    # Cached on second call (no rebuild) — the exact cached tuple is returned.
    cached = s.hierarchy_cache[("/tmp/x.gpkg", "vocab")]
    assert s.get_hierarchy_for_layer(layer) is cached


def test_get_hierarchy_cache_keyed_by_source():
    layer1 = FakeVocabLayer("/tmp/a.gpkg|layername=v1", _features([("http://a", None, "A")]))
    layer2 = FakeVocabLayer("/tmp/b.gpkg|layername=v2", _features([("http://b", None, "B")]))
    s = QskosState()
    _, labels1 = s.get_hierarchy_for_layer(layer1)
    _, labels2 = s.get_hierarchy_for_layer(layer2)
    assert labels1 == {"http://a": "A"}
    assert labels2 == {"http://b": "B"}
    assert len(s.hierarchy_cache) == 2


def test_get_hierarchy_cache_shared_across_layers_same_vocab():
    # Two layers bound to the same vocab table share one cached hierarchy.
    layer1 = FakeVocabLayer("/tmp/x.gpkg|layername=vocab", _features([("http://a", None, "A")]))
    layer2 = FakeVocabLayer("/tmp/x.gpkg|layername=vocab", _features([("http://a", None, "A")]))
    s = QskosState()
    s.get_hierarchy_for_layer(layer1)
    s.get_hierarchy_for_layer(layer2)
    assert len(s.hierarchy_cache) == 1


def test_invalidate_vocab_cache():
    layer = FakeVocabLayer("/tmp/x.gpkg|layername=vocab", _features([("http://a", None, "A")]))
    s = QskosState()
    s.get_hierarchy_for_layer(layer)
    assert len(s.hierarchy_cache) == 1
    s.invalidate_vocab_cache("/tmp/x.gpkg", "vocab")
    assert s.hierarchy_cache == {}
