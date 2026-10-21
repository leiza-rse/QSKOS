# conftest.py
# qskos QGIS Plugin - pytest configuration
# Makes the plugin's pure subpackages importable for unit tests without a QGIS
# runtime:
#   - qskos/libs/ -> bundled rdflib/pyparsing/isodate (same copies QGIS loads)
#   - qskos/      -> the plugin package directory, so `import utils.fields` and
#                    `import tabs.*` resolve as top-level packages.
#
# We add qskos/ (not qskos/utils) to sys.path: Python looks for `utils/__init__.py`
# inside each path entry, so the entry must be the PARENT of utils/. This lets
# tests import the pure subpackages without ever importing qskos/__init__.py
# (the QGIS entry point, which imports PyQt5/QGIS). Because tests/ lives at the
# repo root, outside the plugin package, pytest never imports the plugin root.

import os
import sys

_PLUGIN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "qskos"
)

_LIBS_DIR = os.path.join(_PLUGIN_DIR, "libs")
if os.path.isdir(_LIBS_DIR) and _LIBS_DIR not in sys.path:
    sys.path.insert(0, _LIBS_DIR)

if os.path.isdir(_PLUGIN_DIR) and _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)
