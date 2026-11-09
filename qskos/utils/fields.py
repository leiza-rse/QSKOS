# fields.py
# qskos QGIS Plugin - Field Utilities
# Reading annotation values.  Annotation fields are GeoPackage JSON fields
# (QVariant.Map in QGIS); the ValueRelation widget stores the selected concept
# URIs there as a JSON array, which PyQGIS hands back as a Python list.
# parse_field_value also tolerates the string shapes older plugin versions
# wrote (JSON text, '{a,b}' Postgres-style arrays, pipe-separated).

import json


def parse_field_value(val):
    """
    Parse an annotation field value into a list of URIs.

    The normal shape is a list (JSON field).  Strings are parsed leniently
    (JSON array text, '{a,b}', 'a|b', a bare URI) so data written into the
    text fields of earlier plugin versions keeps working.  NULL -> [].
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