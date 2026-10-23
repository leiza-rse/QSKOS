#!/usr/bin/env bash
# run_qgis_tests.sh
# qskos QGIS Plugin - run the QGIS-bound / end-to-end test suite inside a real
# QGIS Python environment (offscreen), using pytest-qgis.
#
# Works in WSL (after scripts/install_qgis_ubuntu.sh) and in CI (the
# qgis-tests job in .github/workflows/test.yml runs this same script).
#
# Usage:  scripts/run_qgis_tests.sh [pytest args...]
#
# Requires: QGIS installed and a uv venv at .venv-qgis with pytest + pytest-qgis
# (see scripts/install_qgis_ubuntu.sh). QT_QPA_PLATFORM=offscreen runs headless.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

VENV_DIR="${VENV_DIR:-$REPO_ROOT/.venv-qgis}"
PYBIN="$VENV_DIR/bin/python"

if [ ! -x "$PYBIN" ]; then
    echo "error: QGIS test venv not found at $PYBIN" >&2
    echo "Run:  sudo scripts/install_qgis_ubuntu.sh" >&2
    exit 1
fi

echo "==> Running QGIS-bound tests with $PYBIN (offscreen)"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
export QGIS_NO_OVERRIDE_IMPORT=1

# Point Python at the bundled pure deps, matching qskos/__init__.py, so that
# tests and plugin share the same rdflib.
export PYTHONPATH="$REPO_ROOT/qskos:$REPO_ROOT/qskos/libs${PYTHONPATH:+:$PYTHONPATH}"

"$PYBIN" -m pytest tests/test_qgis_plugin.py tests/test_qgis_e2e.py "$@"
