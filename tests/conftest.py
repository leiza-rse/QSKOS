# conftest.py
# qskos QGIS Plugin - pytest configuration
#
# The plugin's pure modules use relative imports (e.g. `from .utils.hierarchy
# import ...`) so they work inside QGIS as the `qskos` package. To unit-test
# them without a QGIS runtime, we register a lightweight `qskos` package in
# sys.modules WITHOUT executing qskos/__init__.py (which imports PyQt5/QGIS).
# The pure subpackages (utils/, tabs/) are then loaded by path with correct
# package context, so their relative imports resolve.

import importlib.util
import os
import sys
import types

_PLUGIN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "qskos"
)

# Bundled pure-Python dependencies (rdflib, pyparsing, isodate) — the same
# copies QGIS loads at runtime.
_LIBS_DIR = os.path.join(_PLUGIN_DIR, "libs")
if os.path.isdir(_LIBS_DIR) and _LIBS_DIR not in sys.path:
    sys.path.insert(0, _LIBS_DIR)


def _register_package(name, pkg_path):
    """Register a package in sys.modules by loading its __init__.py."""
    if name in sys.modules:
        return sys.modules[name]
    init_file = os.path.join(pkg_path, "__init__.py")
    spec = importlib.util.spec_from_file_location(
        name, init_file, submodule_search_locations=[pkg_path]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Lightweight `qskos` package (no __init__.py execution → no PyQt5/QGIS).
_qskos = types.ModuleType("qskos")
_qskos.__path__ = [_PLUGIN_DIR]
sys.modules["qskos"] = _qskos

_register_package("qskos.utils", os.path.join(_PLUGIN_DIR, "utils"))
_register_package("qskos.tabs", os.path.join(_PLUGIN_DIR, "tabs"))
