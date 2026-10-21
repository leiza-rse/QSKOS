# fields.py
# qskos QGIS Plugin - Field Utilities
# Canonical (de)serialisation of annotation values plus a lenient reader for
# legacy data.  The canonical on-disk representation of an annotation field is
# a JSON-encoded list of concept URIs, e.g. '["uri1","uri2"]'.

import json


def encode_annotation_values(values):
    """
    Canonical serialisation of a list of concept URIs into the on-disk
    representation (a JSON array string).  Returns '[]' for empty/None input.
    """
    if not values:
        return "[]"
    cleaned = [str(v).strip() for v in values if str(v).strip()]
    return json.dumps(cleaned, ensure_ascii=False)


def parse_field_value(val):
    """
    Parse an annotation field value into a list of URIs.

    The canonical form is a JSON array string; this function also tolerates
    legacy shapes (a real list, PostgreSQL array, pipe-separated, a bare
    string) so previously-created annotation data keeps displaying/exporting.
    New data is always written via encode_annotation_values.
    """
    if val is None:
        return []
    if isinstance(val, (list, tuple)):
        return [str(v).strip() for v in val if str(v).strip()]
    if isinstance(val, str):
        return _parse_string_value(val)
    return []


def find_annotation_field_names(field_names, concept_labels):
    """
    Return the subset of field_names whose name is a known concept URI in
    concept_labels. This detects annotation fields from a bound vocabulary's
    concept URIs (not by field-type sniffing).
    """
    return [name for name in field_names if name in concept_labels]


def _parse_string_value(s):
    """Parse a single string value into a list of URIs (lenient)."""
    s = s.strip()
    if not s:
        return []

    # Canonical / legacy JSON array
    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except (ValueError, TypeError):
            pass  # not valid JSON — fall through

    # PostgreSQL array, e.g. {a,b}
    if s.startswith("{") and s.endswith("}"):
        inner = s[1:-1]
        if inner:
            return [p.strip().strip('"') for p in inner.split(",") if p.strip()]
        return []

    # Pipe-separated (used by older CSV-imported vocabularies)
    if "|" in s:
        return [part.strip() for part in s.split("|") if part.strip()]

    # Single value
    return [s]