# test_state.py
# qskos QGIS Plugin - unit tests for the shared QskosState object (state.py).
# Verifies that the typed cross-tab state replaces the old ad-hoc plugin
# globals and that the hierarchy cache is keyed per layer.

from qskos.state import QskosState


class FakeVocabLayer:
    """Minimal stand-in for a QGIS vocab layer: id() + getFeatures()."""

    def __init__(self, layer_id, features):
        self._id = layer_id
        self._features = features

    def id(self):
        return self._id

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
    layer = FakeVocabLayer("L1", _features([
        ("http://root", None, "Root"),
        ("http://child", "http://root", "Child"),
    ]))
    s = QskosState()
    children, labels = s.get_hierarchy_for_layer(layer)
    assert labels == {"http://root": "Root", "http://child": "Child"}
    assert children[None] == ["http://root"]
    assert children["http://root"] == ["http://child"]
    # Cached on second call (no rebuild) — the exact cached tuple is returned.
    cached = s.hierarchy_cache["L1"]
    assert s.get_hierarchy_for_layer(layer) is cached


def test_get_hierarchy_cache_keyed_by_layer_id():
    layer1 = FakeVocabLayer("L1", _features([("http://a", None, "A")]))
    layer2 = FakeVocabLayer("L2", _features([("http://b", None, "B")]))
    s = QskosState()
    _, labels1 = s.get_hierarchy_for_layer(layer1)
    _, labels2 = s.get_hierarchy_for_layer(layer2)
    assert labels1 == {"http://a": "A"}
    assert labels2 == {"http://b": "B"}
    assert len(s.hierarchy_cache) == 2
