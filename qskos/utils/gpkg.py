# gpkg.py
# qskos QGIS Plugin - GeoPackage Manager
# All SQLite/GeoPackage read-write operations and shared constants.
# Pure data access — NO QGIS imports, so it is unit-tested without a QGIS
# runtime. QGIS layer adapters (loading hidden vocab layers, extracting layer
# source paths) live in utils/layers.py.

import hashlib
import os
import re
import sqlite3

# ─── Shared constants ─────────────────────────────────────────────────────────
# Import these everywhere instead of repeating string literals.

CONFIG_TABLE   = "qskos_layer_config"
ROLE_VOCAB     = "ConceptScheme"
ROLE_FEATURE   = "FeatureLayer"
INTERNAL_GROUP = "qskos [internal]"

# Vocabulary attribute table column names (no skos: prefix, SQLite-safe)
F_CONCEPT = "concept"
F_LABEL   = "prefLabel"
F_DEF     = "definition"
F_BROADER = "broader"
F_SCHEME  = "inScheme"


# ─── Path helpers ─────────────────────────────────────────────────────────────

def norm_path(p):
    """Normalise a file path for cross-platform string comparison."""
    return os.path.normcase(os.path.normpath(p)) if p else ""


def gpkg_path_from_source(src):
    """Extract the GPKG file path from an OGR layer source string (pure)."""
    return src.split("|")[0] if "|" in src else src


def table_name_from_source(src):
    """Extract the table name from an OGR layer source string (pure)."""
    if "|layername=" in src:
        return src.split("|layername=")[-1].split("|")[0]
    return ""


VOCAB_TABLE_PREFIX = "qskos_vocab_"


def vocab_table_name(scheme_uri):
    """
    GPKG table name for a vocabulary: 'qskos_vocab_<slug>_<hash>'.

    The slug (last URI segment) keeps it readable; the hash of the full scheme
    URI makes it unique per scheme, so two schemes ending in the same segment
    ('.../a/scheme', '.../b/scheme') never share a table, and the prefix keeps
    it from ever matching a user's feature table.
    """
    slug = re.split(r"[/#]", scheme_uri.rstrip("/#"))[-1]
    slug = re.sub(r"[^a-zA-Z0-9_]", "_", slug)[:40].strip("_") or "vocab"
    digest = hashlib.sha1(scheme_uri.encode("utf-8")).hexdigest()[:8]
    return f"{VOCAB_TABLE_PREFIX}{slug}_{digest}"


# ─── Config table ─────────────────────────────────────────────────────────────

def ensure_config_table(gpkg_path):
    """Create qskos_layer_config in the GPKG if it does not exist. Safe to call repeatedly."""
    conn = sqlite3.connect(gpkg_path)
    try:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {CONFIG_TABLE} (
                layer_name  TEXT NOT NULL,
                layer_role  TEXT NOT NULL,
                scheme_uri  TEXT NOT NULL,
                language    TEXT,
                PRIMARY KEY (layer_name, scheme_uri)
            )
        """)
        conn.commit()
    finally:
        conn.close()


def read_config(gpkg_path):
    """Return all rows from qskos_layer_config as a list of dicts."""
    ensure_config_table(gpkg_path)
    conn = sqlite3.connect(gpkg_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(f"SELECT * FROM {CONFIG_TABLE}").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_vocab_entries(gpkg_path):
    """Return config rows for vocabulary layers only."""
    return [r for r in read_config(gpkg_path) if r["layer_role"] == ROLE_VOCAB]


def get_bound_vocab_schemes(gpkg_path, feature_layer_name):
    """Return list of scheme_uris bound to a named feature layer table."""
    return [
        r["scheme_uri"] for r in read_config(gpkg_path)
        if r["layer_role"] == ROLE_FEATURE and r["layer_name"] == feature_layer_name
    ]


def find_vocab_table_for_scheme(gpkg_path, scheme_uri):
    """Return the GPKG table name for a vocab with the given scheme_uri, or None."""
    for r in read_config(gpkg_path):
        if r["layer_role"] == ROLE_VOCAB and r["scheme_uri"] == scheme_uri:
            return r["layer_name"]
    return None


def find_vocab_language(gpkg_path, scheme_uri):
    """Return the stored import language for a vocab. Defaults to 'en'."""
    for r in read_config(gpkg_path):
        if r["layer_role"] == ROLE_VOCAB and r["scheme_uri"] == scheme_uri:
            return r.get("language") or "en"
    return "en"


def scheme_exists_in_gpkg(gpkg_path, scheme_uri):
    """True if a vocab with this scheme_uri is already registered."""
    return find_vocab_table_for_scheme(gpkg_path, scheme_uri) is not None


def bind_feature_to_vocab(gpkg_path, feature_layer_name, scheme_uri):
    """Register a feature-layer → vocab binding row. INSERT OR IGNORE (idempotent)."""
    ensure_config_table(gpkg_path)
    conn = sqlite3.connect(gpkg_path)
    try:
        conn.execute(
            f"INSERT OR IGNORE INTO {CONFIG_TABLE} "
            f"(layer_name, layer_role, scheme_uri) VALUES (?,?,?)",
            (feature_layer_name, ROLE_FEATURE, scheme_uri),
        )
        conn.commit()
    finally:
        conn.close()


def unbind_feature_from_vocab(gpkg_path, feature_layer_name, scheme_uri):
    """Remove a specific feature-layer → vocab binding row."""
    conn = sqlite3.connect(gpkg_path)
    try:
        conn.execute(
            f"DELETE FROM {CONFIG_TABLE} "
            f"WHERE layer_name=? AND layer_role=? AND scheme_uri=?",
            (feature_layer_name, ROLE_FEATURE, scheme_uri),
        )
        conn.commit()
    finally:
        conn.close()


# ─── Vocabulary import ────────────────────────────────────────────────────────

def _table_for_import(rows, scheme_uri):
    """
    Pick the table to (re)write for scheme_uri.  A scheme that is already
    registered keeps its table — including legacy names from older versions —
    unless another scheme is registered on the same table (a collision left by
    the old naming), in which case it gets a fresh table of its own.
    """
    vocab_rows = [r for r in rows if r["layer_role"] == ROLE_VOCAB]
    for r in vocab_rows:
        if r["scheme_uri"] == scheme_uri:
            shared = any(
                o["layer_name"] == r["layer_name"] and o["scheme_uri"] != scheme_uri
                for o in vocab_rows
            )
            if not shared:
                return r["layer_name"]
    return vocab_table_name(scheme_uri)


_VOCAB_COLUMNS = ("fid", F_CONCEPT, F_LABEL, F_DEF, F_BROADER, F_SCHEME)


def import_vocab_to_gpkg(concepts, scheme_uri, lang, gpkg_path):
    """
    Write SKOS concepts as a non-spatial attribute table in the GPKG and
    register it in qskos_layer_config.  Replaces the vocabulary's previous
    content — caller MUST confirm with the user when scheme_exists_in_gpkg()
    is True.

    An existing table is emptied and refilled rather than dropped, so a QGIS
    layer that already has it open stays valid (call layer.reload() after).

    Expects concepts as dicts with keys: concept, prefLabel, definition,
    broader, inScheme  (as produced by skos.load_skos_source).

    Returns the table name.
    """
    rows = read_config(gpkg_path)
    table_name = _table_for_import(rows, scheme_uri)

    conn = sqlite3.connect(gpkg_path)
    try:
        cols = tuple(
            r[1] for r in conn.execute(f'PRAGMA table_info("{table_name}")')
        )
        if cols and cols != _VOCAB_COLUMNS:
            raise ValueError(
                f"Table '{table_name}' exists but is not a qskos vocabulary "
                f"table (columns: {', '.join(cols)}); refusing to overwrite it."
            )
        if cols:
            conn.execute(f'DELETE FROM "{table_name}"')
        else:
            conn.execute(f"""
                CREATE TABLE "{table_name}" (
                    fid       INTEGER PRIMARY KEY AUTOINCREMENT,
                    {F_CONCEPT}  TEXT,
                    {F_LABEL}    TEXT,
                    {F_DEF}      TEXT,
                    {F_BROADER}  TEXT,
                    {F_SCHEME}   TEXT
                )
            """)
        conn.executemany(
            f'INSERT INTO "{table_name}" '
            f"({F_CONCEPT},{F_LABEL},{F_DEF},{F_BROADER},{F_SCHEME}) "
            f"VALUES (?,?,?,?,?)",
            [
                (
                    c.get("concept", ""),
                    c.get("prefLabel", ""),
                    c.get("definition", ""),
                    c.get("broader") or "",
                    c.get("inScheme") or "",
                )
                for c in concepts
            ],
        )
        # Register in gpkg_contents so OGR/QGIS recognises it as an attribute table
        try:
            conn.execute(
                "INSERT OR REPLACE INTO gpkg_contents "
                "(table_name, data_type, identifier, description, last_change) "
                "VALUES (?, 'attributes', ?, '', strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
                (table_name, table_name),
            )
        except sqlite3.OperationalError:
            pass  # gpkg_contents absent in plain SQLite files — layer still loads via OGR

        # One registration row per scheme (drop a stale row on another table).
        conn.execute(
            f"DELETE FROM {CONFIG_TABLE} WHERE layer_role=? AND scheme_uri=?",
            (ROLE_VOCAB, scheme_uri),
        )
        conn.execute(
            f"INSERT INTO {CONFIG_TABLE} "
            f"(layer_name, layer_role, scheme_uri, language) VALUES (?,?,?,?)",
            (table_name, ROLE_VOCAB, scheme_uri, lang),
        )
        conn.commit()
    finally:
        conn.close()

    return table_name
