# fields.py
# qskos QGIS Plugin - Field Utilities
# Handles annotation field creation and value parsing.

from PyQt5.QtCore import QVariant


# 👇 NEW: Robust field value parser — no assumptions about URI format
def parse_field_value(val):
    """
    Robustly parse annotation field value into list of URIs.
    Handles: list, string (JSON, PostgreSQL array, pipe-separated), QVariant.
    """
    if isinstance(val, QVariant) and val.isNull():
        return []
    if isinstance(val, list):
        return [str(v).strip() for v in val if isinstance(v, str) and v.strip()]
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        # Try JSON
        if s.startswith('[') and s.endswith(']'):
            try:
                import json
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if isinstance(x, str) and x.strip()]
            except:
                pass
        # PostgreSQL array
        if s.startswith('{') and s.endswith('}'):
            try:
                # Use QGIS expression parser for safety
                from qgis.core import QgsExpression
                exp = QgsExpression(f"string_to_array(trim(both '{{}}' from '{s}'), ',')")
                result = exp.evaluate()
                if isinstance(result, list):
                    # Unescape double quotes
                    return [x.replace('""', '"').strip().strip('"') for x in result if isinstance(x, str) and x.strip()]
            except:
                pass
        # Pipe-separated
        if '|' in s:
            return [part.strip() for part in s.split('|') if part.strip()]
        # Single value
        return [s]
    return []