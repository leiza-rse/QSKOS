# test_gpkg.py
# qskos QGIS Plugin - unit tests for utils/gpkg.py (pure SQLite/GeoPackage
# access). No QGIS runtime required.

import sqlite3

from qskos.utils.gpkg import (
    ensure_config_table,
    has_qskos_config,
    read_vocab_rows,
    split_vocab_source_key,
    vocab_source_key,
    read_config,
    get_vocab_entries,
    get_bound_vocab_schemes,
    find_vocab_table_for_scheme,
    find_vocab_language,
    scheme_exists_in_gpkg,
    bind_feature_to_vocab,
    unbind_feature_from_vocab,
    import_vocab_to_gpkg,
    vocab_table_name,
    norm_path,
    CONFIG_TABLE,
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


class TestHasQskosConfig:
    def test_true_for_qskos_gpkg(self, tmp_path):
        gpkg = str(tmp_path / "x.gpkg")
        ensure_config_table(gpkg)
        assert has_qskos_config(gpkg)

    def test_missing_file_is_not_created(self, tmp_path):
        gpkg = tmp_path / "missing.gpkg"
        assert not has_qskos_config(str(gpkg))
        assert not gpkg.exists()

    def test_other_sqlite_file_is_left_untouched(self, tmp_path):
        gpkg = tmp_path / "other.gpkg"
        conn = sqlite3.connect(gpkg)
        conn.execute("CREATE TABLE roads (id INTEGER)")
        conn.commit()
        conn.close()
        before = gpkg.read_bytes()
        assert not has_qskos_config(str(gpkg))
        assert gpkg.read_bytes() == before

    def test_non_sqlite_and_odd_paths(self, tmp_path):
        shp = tmp_path / "a b#?%.shp"
        shp.write_bytes(b"not sqlite")
        assert not has_qskos_config(str(shp))
        assert not has_qskos_config("")
        assert not has_qskos_config(None)


class TestVocabCopySource:
    def test_read_vocab_rows_is_read_only_and_complete(self, tmp_path):
        gpkg = tmp_path / "x.gpkg"
        table = import_vocab_to_gpkg(
            [{"concept": "http://e.org/a", "prefLabel": "A", "definition": None,
              "broader": None, "inScheme": "http://e.org/s"},
             {"concept": "http://e.org/b", "prefLabel": "B", "definition": "d",
              "broader": "http://e.org/a", "inScheme": "http://e.org/s"}],
            "http://e.org/s", "en", str(gpkg))
        before = gpkg.read_bytes()
        assert read_vocab_rows(str(gpkg), table) == [
            ("http://e.org/a", "A", "", "", "http://e.org/s"),
            ("http://e.org/b", "B", "d", "http://e.org/a", "http://e.org/s"),
        ]
        assert gpkg.read_bytes() == before

    def test_source_key_roundtrip(self, tmp_path):
        key = vocab_source_key(str(tmp_path / "a.gpkg"), "qskos_vocab_x_1")
        assert split_vocab_source_key(key) == (
            norm_path(str(tmp_path / "a.gpkg")), "qskos_vocab_x_1")


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
        assert table == vocab_table_name("http://scheme")
        assert table.startswith("qskos_vocab_scheme_")
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
        assert find_vocab_table_for_scheme(gpkg, "http://scheme") == \
            vocab_table_name("http://scheme")
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


def _concepts(scheme, *uris):
    return [{"concept": u, "prefLabel": u[-1], "definition": "",
             "broader": None, "inScheme": scheme} for u in uris]


def _table_rows(gpkg, table):
    conn = sqlite3.connect(gpkg)
    try:
        return sorted(r[0] for r in conn.execute(f'SELECT concept FROM "{table}"'))
    finally:
        conn.close()


class TestVocabTableIsolation:
    """Regression: two schemes ending in the same path segment used to share
    (and overwrite) one table, breaking the first vocabulary's tree and
    annotation widgets."""

    def test_same_last_segment_gets_separate_tables(self, tmp_path):
        gpkg = str(tmp_path / "x.gpkg")
        t1 = import_vocab_to_gpkg(_concepts("http://a.org/scheme", "http://a/1"),
                                  "http://a.org/scheme", "en", gpkg)
        t2 = import_vocab_to_gpkg(_concepts("http://b.org/scheme", "http://b/1"),
                                  "http://b.org/scheme", "en", gpkg)
        assert t1 != t2
        assert _table_rows(gpkg, t1) == ["http://a/1"]
        assert _table_rows(gpkg, t2) == ["http://b/1"]

    def test_never_targets_a_feature_table(self, tmp_path):
        gpkg = str(tmp_path / "x.gpkg")
        conn = sqlite3.connect(gpkg)
        conn.execute("CREATE TABLE objects (fid INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO objects (name) VALUES ('keep me')")
        conn.commit()
        conn.close()
        import_vocab_to_gpkg(_concepts("http://x.org/objects", "http://x/1"),
                             "http://x.org/objects", "en", gpkg)
        conn = sqlite3.connect(gpkg)
        assert conn.execute("SELECT name FROM objects").fetchall() == [("keep me",)]
        conn.close()

    def test_reimport_reuses_table_and_replaces_content(self, tmp_path):
        gpkg = str(tmp_path / "x.gpkg")
        t1 = import_vocab_to_gpkg(_concepts("http://s", "http://old"),
                                  "http://s", "en", gpkg)
        t2 = import_vocab_to_gpkg(_concepts("http://s", "http://new"),
                                  "http://s", "de", gpkg)
        assert t1 == t2
        assert _table_rows(gpkg, t1) == ["http://new"]
        entries = get_vocab_entries(gpkg)
        assert len(entries) == 1 and entries[0]["language"] == "de"

    def test_legacy_table_name_is_kept_on_reimport(self, tmp_path):
        gpkg = str(tmp_path / "x.gpkg")
        ensure_config_table(gpkg)
        conn = sqlite3.connect(gpkg)
        conn.execute("CREATE TABLE scheme (fid INTEGER PRIMARY KEY AUTOINCREMENT,"
                     " concept TEXT, prefLabel TEXT, definition TEXT,"
                     " broader TEXT, inScheme TEXT)")
        conn.execute(f"INSERT INTO {CONFIG_TABLE} VALUES ('scheme', ?, 'http://a/scheme', 'en')",
                     (ROLE_VOCAB,))
        conn.commit()
        conn.close()
        t = import_vocab_to_gpkg(_concepts("http://a/scheme", "http://a/1"),
                                 "http://a/scheme", "en", gpkg)
        assert t == "scheme"

    def test_legacy_shared_table_is_split_on_reimport(self, tmp_path):
        gpkg = str(tmp_path / "x.gpkg")
        ensure_config_table(gpkg)
        conn = sqlite3.connect(gpkg)
        for scheme in ("http://a/scheme", "http://b/scheme"):
            conn.execute(f"INSERT INTO {CONFIG_TABLE} VALUES ('scheme', ?, ?, 'en')",
                         (ROLE_VOCAB, scheme))
        conn.commit()
        conn.close()
        t = import_vocab_to_gpkg(_concepts("http://a/scheme", "http://a/1"),
                                 "http://a/scheme", "en", gpkg)
        assert t == vocab_table_name("http://a/scheme")
        assert find_vocab_table_for_scheme(gpkg, "http://a/scheme") == t
        assert find_vocab_table_for_scheme(gpkg, "http://b/scheme") == "scheme"

    def test_refuses_to_overwrite_foreign_table(self, tmp_path):
        import pytest
        gpkg = str(tmp_path / "x.gpkg")
        conn = sqlite3.connect(gpkg)
        conn.execute(f'CREATE TABLE "{vocab_table_name("http://s")}" (x TEXT)')
        conn.commit()
        conn.close()
        with pytest.raises(ValueError):
            import_vocab_to_gpkg(_concepts("http://s", "http://1"),
                                 "http://s", "en", gpkg)


class TestNormPath:
    def test_normalises(self):
        assert norm_path("a/b/c.gpkg") == norm_path("a/b/c.gpkg")

    def test_empty(self):
        assert norm_path(None) == ""
        assert norm_path("") == ""
