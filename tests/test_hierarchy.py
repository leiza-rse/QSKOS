# test_hierarchy.py
# qskos QGIS Plugin - unit tests for utils/hierarchy.py (pure BFS/index).
# No QGIS runtime required.

from qskos.utils.hierarchy import (
    build_hierarchy_index,
    get_descendant_uris_fast,
)


class FakeVocabLayer:
    def __init__(self, features):
        self._features = features

    def getFeatures(self):
        return iter(self._features)


def _features(rows):
    return [
        {"concept": uri, "broader": broader, "prefLabel": label}
        for uri, broader, label in rows
    ]


class TestBuildHierarchyIndex:
    def test_roots_and_children(self):
        children, labels = build_hierarchy_index(FakeVocabLayer(_features([
            ("http://r", None, "Root"),
            ("http://a", "http://r", "A"),
            ("http://b", "http://a", "B"),
        ])))
        assert children[None] == ["http://r"]
        assert children["http://r"] == ["http://a"]
        assert children["http://a"] == ["http://b"]
        assert labels == {
            "http://r": "Root", "http://a": "A", "http://b": "B"
        }

    def test_empty_broader_treated_as_root(self):
        children, _ = build_hierarchy_index(FakeVocabLayer(_features([
            ("http://r", "", "Root"),
        ])))
        assert children[None] == ["http://r"]


class TestDescendants:
    def _index(self):
        return build_hierarchy_index(FakeVocabLayer(_features([
            ("http://r", None, "Root"),
            ("http://a", "http://r", "A"),
            ("http://b", "http://a", "B"),
            ("http://c", "http://b", "C"),
        ])))[0]

    def test_includes_root(self):
        idx = self._index()
        assert set(get_descendant_uris_fast(idx, "http://r")) == {
            "http://r", "http://a", "http://b", "http://c"
        }

    def test_subtree(self):
        idx = self._index()
        assert set(get_descendant_uris_fast(idx, "http://a")) == {
            "http://a", "http://b", "http://c"
        }

    def test_leaf_returns_self(self):
        idx = self._index()
        assert get_descendant_uris_fast(idx, "http://c") == ["http://c"]

    def test_handles_cycle(self):
        children = build_hierarchy_index(FakeVocabLayer(_features([
            ("http://a", "http://b", "A"),
            ("http://b", "http://a", "B"),
        ])))[0]
        # Must terminate despite the cycle.
        desc = get_descendant_uris_fast(children, "http://a")
        assert set(desc) == {"http://a", "http://b"}
