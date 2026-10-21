# test_gpkg.py
# qskos QGIS Plugin - unit tests for utils/gpkg.py (pure SQLite/GeoPackage
# access). No QGIS runtime required.

import sqlite3

from qskos.utils.gpkg import (
    ensure_config_table,
    read_config,
    get_vocab_entries,
    get_bound_vocab_schemes,
    find_vocab_table_for_scheme,
    find_vocab_language,
    scheme_exists_in_gpkg,
    bind_feature_to_vocab,
    unbind_feature_from_vocab,
    import_vocab_to_gpkg,
    norm_path,
    ROLE_VOCAB,
    ROLE_FEATURE,
)


class TestConfigTable:
    def test_ensure_creates_table(self, tmp_path):
        gpkg = str(tmp_path / "x.gpkg")
        ensure_config_table(gpkg)
        conn = sqlite3.connect(gpkg)
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        assert any(r[0] == "qskos_layer_config" for r in rows)

    def test_ensure_is_idempotent(self, tmp_path):
        gpkg = str(tmp_path / "x.gpkg")
        ensure_config_table(gpkg)
        ensure_config_table(gpkg)  # must not raise

    def test_read_config_empty(self, tmp_path):
        gpkg = str(tmp_path / "x.gpkg")
        ensure_config_table(gpkg)
        assert read_config(gpkg) == []


class TestBinding:
    def _setup(self, tmp_path):
        gpkg = str(tmp_path / "x.gpkg")
        ensure_config_table(gpkg)
        import_vocab_to_gpkg(
            [{"concept": "http://a", "prefLabel": "A", "definition": "",
              "broader": None, "inScheme": "http://s"}],
            "http://s", "en", gpkg,
        )
        return gpkg

    def test_bind_and_read(self, tmp_path):
        gpkg = self._setup(tmp_path)
        bind_feature_to_vocab(gpkg, "layer1", "http://s")
        assert get_bound_vocab_schemes(gpkg, "layer1") == ["http://s"]

    def test_bind_idempotent(self, tmp_path):
        gpkg = self._setup(tmp_path)
        bind_feature_to_vocab(gpkg, "layer1", "http://s")
        bind_feature_to_vocab(gpkg, "layer1", "http://s")
        assert get_bound_vocab_schemes(gpkg, "layer1") == ["http://s"]

    def test_unbind(self, tmp_path):
        gpkg = self._setup(tmp_path)
        bind_feature_to_vocab(gpkg, "layer1", "http://s")
        unbind_feature_from_vocab(gpkg, "layer1", "http://s")
        assert get_bound_vocab_schemes(gpkg, "layer1") == []

    def test_bound_only_for_named_layer(self, tmp_path):
        gpkg = self._setup(tmp_path)
        bind_feature_to_vocab(gpkg, "layer1", "http://s")
        assert get_bound_vocab_schemes(gpkg, "other") == []


class TestVocabImport:
    def test_import_creates_table_and_registers(self, tmp_path):
        gpkg = str(tmp_path / "x.gpkg")
        table = import_vocab_to_gpkg(
            [{"concept": "http://a", "prefLabel": "A", "definition": "d",
              "broader": None, "inScheme": "http://s"}],
            "http://scheme", "de", gpkg,
        )
        assert table == "scheme"
        entries = get_vocab_entries(gpkg)
        assert len(entries) == 1
        assert entries[0]["scheme_uri"] == "http://scheme"
        assert entries[0]["language"] == "de"
        assert entries[0]["layer_role"] == ROLE_VOCAB

    def test_import_roundtrips_concepts(self, tmp_path):
        gpkg = str(tmp_path / "x.gpkg")
        concepts = [
            {"concept": "http://a", "prefLabel": "A", "definition": "d1",
             "broader": None, "inScheme": "http://s"},
            {"concept": "http://b", "prefLabel": "B", "definition": "d2",
             "broader": "http://a", "inScheme": "http://s"},
        ]
        table = import_vocab_to_gpkg(concepts, "http://scheme", "en", gpkg)
        conn = sqlite3.connect(gpkg)
        rows = conn.execute(
            f"SELECT concept, prefLabel, broader FROM '{table}'"
        ).fetchall()
        conn.close()
        assert ("http://a", "A", "") in rows
        assert ("http://b", "B", "http://a") in rows

    def test_find_vocab_table_and_language(self, tmp_path):
        gpkg = str(tmp_path / "x.gpkg")
        import_vocab_to_gpkg(
            [{"concept": "http://a", "prefLabel": "A", "definition": "",
              "broader": None, "inScheme": "http://s"}],
            "http://scheme", "en", gpkg,
        )
        assert find_vocab_table_for_scheme(gpkg, "http://scheme") == "scheme"
        assert find_vocab_language(gpkg, "http://scheme") == "en"
        assert find_vocab_language(gpkg, "http://missing") == "en"

    def test_scheme_exists(self, tmp_path):
        gpkg = str(tmp_path / "x.gpkg")
        import_vocab_to_gpkg(
            [{"concept": "http://a", "prefLabel": "A", "definition": "",
              "broader": None, "inScheme": "http://s"}],
            "http://scheme", "en", gpkg,
        )
        assert scheme_exists_in_gpkg(gpkg, "http://scheme") is True
        assert scheme_exists_in_gpkg(gpkg, "http://other") is False


class TestNormPath:
    def test_normalises(self):
        assert norm_path("a/b/c.gpkg") == norm_path("a/b/c.gpkg")

    def test_empty(self):
        assert norm_path(None) == ""
        assert norm_path("") == ""
